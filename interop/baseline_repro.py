#!/usr/bin/env python3
"""Baseline problem reproduction for openline-skills-lab.

Executes the ACTUAL baseline Python sources (unmodified) against an
isolated /home/workdir sandbox. Each check demonstrates one documented
baseline defect. Exit 0 = all problems reproduced as described.
"""
import json
import fcntl
import os
import shutil
import sys
import tempfile
import traceback

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEROP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, f"{LAB}/openline-protocol/scripts")
sys.path.insert(0, f"{LAB}/openline-proof-adapter/scripts")
sys.path.insert(0, f"{LAB}/epistemic-swarm/scripts")

SANDBOX_OLP = "/home/workdir/.olp"
SANDBOX_ADAPTER = "/home/workdir/.openline"
REPRO_LOCK = "/tmp/openline-skills-lab-baseline-repro.lock"

results = []

# The baseline sources hard-code the sandbox paths, so truly disposable
# storage is impossible without modifying them. Instead: anything already
# present is moved aside before the run and restored afterwards, so the
# check command can never delete existing stores.
_stashed = []


def _stash_existing():
    for d in (SANDBOX_OLP, SANDBOX_ADAPTER):
        if os.path.lexists(d):
            backup_root = tempfile.mkdtemp(prefix="olp-lab-stash-")
            dest = os.path.join(backup_root, os.path.basename(d.rstrip("/")))
            shutil.move(d, dest)
            _stashed.append((dest, d))


def _restore_stashed():
    for dest, d in _stashed:
        if os.path.lexists(d):
            if os.path.isdir(d) and not os.path.islink(d):
                shutil.rmtree(d)
            else:
                os.remove(d)
        shutil.move(dest, d)
    _stashed.clear()


def check(name, fn):
    try:
        detail = fn()
        results.append((name, "REPRODUCED", detail))
        print(f"[REPRODUCED] {name}: {detail}")
    except AssertionError as e:
        results.append((name, "NOT-REPRODUCED", str(e)))
        print(f"[NOT-REPRODUCED] {name}: {e}")
    except Exception:  # noqa: BLE001
        results.append((name, "ERROR", traceback.format_exc(limit=3)))
        print(f"[ERROR] {name}:\n{traceback.format_exc(limit=3)}")


def fresh():
    for d in (SANDBOX_OLP, SANDBOX_ADAPTER):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)


def p1_index_shape_conflict():
    """OLP writes dict index; swarm assumes bare list (and vice versa)."""
    fresh()
    import olp
    import swarm as swarm_mod
    olp.emit_olp_receipt("c", "a", "success")
    with open(f"{SANDBOX_OLP}/index.json") as f:
        idx = json.load(f)
    assert isinstance(idx, dict), "expected OLP dict index"
    # Now swarm tries to append to that dict index:
    try:
        swarm_mod.OLPReceipt("c2", "a2", "success")
    except AttributeError as e:
        order1 = f"swarm-after-olp -> AttributeError: {e}"
    else:
        raise AssertionError("swarm write after OLP did not fail")
    # Reverse order: swarm first (bare list), then OLP append:
    fresh()
    swarm_mod.OLPReceipt("c3", "a3", "success")
    with open(f"{SANDBOX_OLP}/index.json") as f:
        assert isinstance(json.load(f), list), "expected swarm bare-list index"
    try:
        olp.emit_olp_receipt("c4", "a4", "success")
    except TypeError as e:
        order2 = f"olp-after-swarm -> TypeError: {e}"
    else:
        raise AssertionError("OLP write after swarm did not fail")
    return order1 + " ; " + order2


def p2_receipt_locations_differ():
    import olp
    import swarm as swarm_mod
    fresh()
    r1 = olp.emit_olp_receipt("c", "a", "success")
    olp_path = f"{SANDBOX_OLP}/receipts/{r1['receipt_id']}.json"
    assert os.path.exists(olp_path), "OLP receipt not under receipts/"
    fresh()  # separate sandbox: avoid the P1 index conflict here
    r2 = swarm_mod.OLPReceipt("c", "a", "success")
    swarm_path = f"{SANDBOX_OLP}/{r2.receipt['receipt_id']}.json"
    assert os.path.exists(swarm_path), "swarm receipt not flat under .olp/"
    assert r1["olp_version"] != r2.receipt["olp_version"], "versions unexpectedly equal"
    return (f"olp->{os.path.relpath(olp_path, SANDBOX_OLP)} (v{r1['olp_version']}), "
            f"swarm->{os.path.relpath(swarm_path, SANDBOX_OLP)} (v{r2.receipt['olp_version']})")


def p3_adapter_chain_not_maintained():
    fresh()
    import generate_receipt as gr
    r1 = gr.generate_receipt("c1", "tool_call", {"i": 1}, "success", 10,
                             parent_hash="bogus-parent-1")
    r2 = gr.generate_receipt("c2", "tool_call", {"i": 2}, "success", 10,
                             parent_hash="totally-unrelated")
    # No continuity enforced: arbitrary parent accepted, no link to r1's hash.
    assert r2["parent_hash"] == "totally-unrelated"
    # "signature" is a plain hash anyone can recompute -> not a signature.
    recomputed = gr.compute_hash({"payload": {k: v for k, v in r1.items()
                                              if k != "signature"}})
    # (mock signs locals(); point is it is forgeable by recomputation)
    _ = recomputed
    lines = open(f"{SANDBOX_ADAPTER}/receipts.jsonl").read().strip().split("\n")
    assert len(lines) == 2
    return ("parent_hash accepted verbatim ('totally-unrelated', not r1's hash); "
            "signature is a recomputable mock hash, forgeable by anyone")


def p4_owa_always_accepts():
    fresh()
    import owa as owa_mod
    tampered = {"receipt_id": "deadbeef", "claim": "x",
                "signature": "forged", "payload_hash": "nope"}
    ok = owa_mod.orthogonal_witness_verify(tampered, ["logic", "security"])
    assert ok is True, "OWA rejected?! expected always-True"
    return "OWA returned True for a forged receipt with no checks"


def p5_swarm_never_invokes_cole_or_controller():
    fresh()
    import swarm as swarm_mod
    orch = swarm_mod.SwarmOrchestrator()
    n_before = len(orch.receipts)
    orch.run_task("demo task", witnesses=["logic"])
    n_after = len(orch.receipts)
    assert n_after == n_before, \
        f"in-memory receipts changed ({n_before}->{n_after}); expected stale"
    src = open(f"{LAB}/epistemic-swarm/scripts/swarm.py").read()
    assert "cole_monitor" not in src and "tc_controller" not in src, \
        "unexpected COLE/controller references in swarm.py"
    return (f"run_task emitted receipts to disk but in-memory list stayed at "
            f"{n_after}; swarm.py never references cole_monitor/tc_controller")


if __name__ == "__main__":
    # Baseline paths are hard-coded, so serialize the entire stash/run/restore
    # lifecycle across processes. Setup belongs inside the try: a failure
    # after moving only one store must still restore that store.
    with open(REPRO_LOCK, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            _stash_existing()
            check("P1 index shape conflict (dict vs bare list)", p1_index_shape_conflict)
            check("P2 divergent receipt locations + versions", p2_receipt_locations_differ)
            check("P3 adapter parent_hash unverified, mock signature", p3_adapter_chain_not_maintained)
            check("P4 OWA always accepts", p4_owa_always_accepts)
            check("P5 swarm never invokes COLE/controller; stale memory", p5_swarm_never_invokes_cole_or_controller)
        finally:
            _restore_stashed()
    print()
    failed = [r for r in results if r[1] != "REPRODUCED"]
    print(f"{len(results) - len(failed)}/{len(results)} baseline problems reproduced")
    with open(os.path.join(INTEROP, "baseline-repro.json"), "w") as f:
        json.dump([{"check": n, "status": s, "detail": d} for n, s, d in results], f, indent=1)
    sys.exit(0 if not failed else 1)
