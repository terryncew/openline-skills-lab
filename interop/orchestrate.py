"""Working orchestration over the shared receipt layer.

Fixes the baseline swarm defects:
  - accepts a CALLABLE task executor and records its ACTUAL outcome
    (exceptions become failure receipts, not silent placeholders);
  - in-memory receipt state is updated after EVERY emitted receipt;
  - COLE (baseline cole_monitor) and the Terrynce controller (baseline
    tc_controller) are invoked during execution;
  - drift is measured with a COMPATIBLE noise metric scaled so documented
    drift scenarios can actually trigger rerouting (the baseline COLE
    variance metric maxes out at ~0.04 against 0.35-0.5 thresholds, so it
    can never fire -- that defect is documented, not replicated);
  - witness validators are REAL callables whose verdicts are recorded
    and propagated (the baseline OWA always returned True).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import baseline_shim
from .chain import Signer, public_key_from_hex, verify_receipt
from .schema import new_receipt
from .storage import Storage

Executor = Callable[[str], Dict[str, Any]]
WitnessFn = Callable[[Dict[str, Any], Ed25519PublicKey], "WitnessResult"]


@dataclass
class WitnessResult:
    witness: str
    ok: bool
    detail: str = ""


def chain_witness(receipt: Dict[str, Any],
                  public_key: Ed25519PublicKey) -> WitnessResult:
    """Real witness: verifies payload hash + Ed25519 signature."""
    problems = verify_receipt(receipt, public_key)
    return WitnessResult(
        witness="chain",
        ok=not problems,
        detail="; ".join(problems) if problems else "signature valid",
    )


def drift_epsilon(receipts: List[Dict[str, Any]], window: int = 10) -> float:
    """Compatible noise measurement: recent task-failure fraction in [0, 1].

    Uses the explicit `outcome` field -- never substring matching on
    `result`. Baseline COLE's variance-based epsilon cannot reach the
    documented thresholds; this metric keeps the same (noise, per-domain
    threshold) contract while letting documented drift scenarios trigger
    rerouting.
    """
    recent = [r for r in receipts
              if r.get("action") == "task_complete"][-window:]
    if not recent:
        return 0.0
    bad = sum(1 for r in recent if r.get("outcome") != "success")
    return bad / len(recent)


class Orchestrator:
    def __init__(self, storage: Storage, signer: Signer,
                 public_key_hex: str,
                 witnesses: List[WitnessFn] | None = None,
                 domain: str = "general",
                 fallback_executor: Optional[Executor] = None,
                 witness_name: str = "orchestrator"):
        self.storage = storage
        self.signer = signer
        self.public_key = public_key_from_hex(public_key_hex)
        self.witnesses = witnesses or [chain_witness]
        self.domain = domain
        self.fallback_executor = fallback_executor
        self.witness_name = witness_name
        self._emit_lock = threading.Lock()
        # In-memory state, rebuilt from storage (restart recovery).
        self.receipts: List[Dict[str, Any]] = []
        for rid in self.storage.list_ids():
            try:
                self.receipts.append(self.storage.load(rid))
            except Exception:  # noqa: BLE001 - skip unreadable, keep going
                continue
        # Routing decision persists in the receipts themselves: if a
        # reroute was ever recorded, it stays in effect across restarts.
        # (The fallback *callable* cannot be persisted; the caller must
        # re-supply it when reconstructing the orchestrator.)
        self.rerouted = any(r.get("action") == "reroute"
                            for r in self.receipts)

    # -- internals ------------------------------------------------------
    def _emit(self, claim: str, action: str, result: str,
              evidence: Any = None, tokens_used: int = 0,
              next_use_note: str = "", outcome: str = "success"
              ) -> Dict[str, Any]:
        def build(parent_hash):
            return new_receipt(
                claim=claim, action=action, result=result, evidence=evidence,
                tokens_used=tokens_used, witness=self.witness_name,
                next_use_note=next_use_note, parent_hash=parent_hash,
                outcome=outcome)
        # Head selection, signing, and persistence are one storage
        # transaction; the in-memory append is serialized per-orchestrator.
        with self._emit_lock:
            receipt = self.storage.emit_signed(build, self.signer)
            self.receipts.append(receipt)  # updated after every emit
        return receipt

    def _last_good(self) -> Optional[Dict[str, Any]]:
        for r in reversed(self.receipts):
            if (r.get("action") == "task_complete"
                    and r.get("outcome") == "success"):
                return r
        return None

    # -- public API ------------------------------------------------------
    def run_task(self, task: str, executor: Executor) -> Dict[str, Any]:
        """Execute one task through the full pipeline."""
        active = (self.fallback_executor
                  if (self.rerouted and self.fallback_executor) else executor)
        self._emit(f"Start task: {task}", "task_start", "init",
                   evidence={"task": task})

        try:
            outcome = active(task)
            result = str(outcome.get("result", ""))
            evidence = outcome.get("evidence")
            tokens = int(outcome.get("tokens_used", 0))
            task_outcome = outcome.get("outcome", "success")
        except Exception as e:  # noqa: BLE001 - record actual failure
            result, evidence, tokens = f"failure: {e!r}", {"error": repr(e)}, 0
            task_outcome = "failure"

        done = self._emit(f"Task result: {task}", "task_complete", result,
                          evidence={"output": result, "evidence": evidence},
                          tokens_used=tokens,
                          next_use_note="for witness verification",
                          outcome=task_outcome)

        # Witnesses: real validators, results propagated.
        verdicts = [w(done, self.public_key) for w in self.witnesses]
        accepted = all(v.ok for v in verdicts)
        self._emit(
            f"Witness verdicts for {done['receipt_id'][:8]}",
            "witness_verdicts",
            "accepted" if accepted else "rejected",
            evidence={"verdicts": [
                {"witness": v.witness, "ok": v.ok, "detail": v.detail}
                for v in verdicts]})

        # COLE observation (baseline, recorded) + compatible drift decision.
        cole_obs = baseline_shim.cole_monitor(self.receipts)
        eps = drift_epsilon(self.receipts)
        decision = baseline_shim.tc_controller(
            eps, self.domain, self._last_good())
        self._emit(f"COLE/drift check: eps={eps:.2f}", "drift_check",
                   decision.get("action", "continue"),
                   evidence={"cole": cole_obs, "drift_epsilon": eps,
                             "decision": decision})
        rerouted_now = False
        if decision.get("action") == "reroute" and not self.rerouted:
            self.rerouted = True
            rerouted_now = True
            self._emit("Rerouted after drift", "reroute",
                       f"rerouted to fallback: {decision.get('reason')}",
                       evidence={"decision": decision})

        return {"receipt": done, "accepted": accepted,
                "witnesses": verdicts, "rerouted": rerouted_now,
                "drift_epsilon": eps, "cole": cole_obs}
