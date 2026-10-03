"""Versioned unified receipt schema + legacy converters.

Canonical OLP version: "0.1" (openline-protocol's current version; the
swarm's hard-coded "1.0" is retired).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .canonical import payload_hash_of

RECEIPT_SCHEMA_VERSION = 1
OLP_VERSION = "0.1"  # standardized on the protocol's current version

# Explicit outcome vocabulary. No substring matching on `result` anywhere
# in this package: "unsuccessful" and "not successful" must never read as
# success, and no failure text may become `last_good`.
OUTCOMES = ("success", "failure", "unknown")

REQUIRED_FIELDS = (
    "schema_version", "olp_version", "receipt_id", "claim", "action",
    "result", "outcome", "evidence_hash", "tokens_used", "timestamp",
    "witness", "next_use_note", "parent_hash",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_hash(evidence: Any) -> str:
    if evidence is None:
        return ""
    return payload_hash_of(evidence)


def new_receipt(claim: str, action: str, result: str,
                evidence: Any = None, tokens_used: int = 0,
                witness: str = "", next_use_note: str = "",
                parent_hash: Optional[str] = None,
                timestamp: Optional[str] = None,
                outcome: str = "success") -> Dict[str, Any]:
    """Build an unsigned unified receipt (signing happens in chain.py)."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "olp_version": OLP_VERSION,
        "receipt_id": uuid.uuid4().hex,
        "claim": claim,
        "action": action,
        "result": str(result),
        "outcome": outcome,
        "evidence_hash": evidence_hash(evidence),
        "tokens_used": int(tokens_used),
        "timestamp": timestamp or utc_now_iso(),
        "witness": witness,
        "next_use_note": next_use_note,
        "parent_hash": parent_hash,
    }


def validate_shape(receipt: Dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in receipt]
    if missing:
        raise ValueError(f"receipt missing fields: {missing}")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version: {receipt.get('schema_version')}")


# ---------------------------------------------------------------------------
# Legacy converters. Converted receipts keep their original ids/timestamps
# and carry a `legacy` block that records verification status HONESTLY:
# none of the three baseline formats have cryptographic signatures, so
# signature_verified is always False with the reason stated.
# ---------------------------------------------------------------------------

def legacy_outcome(result: Any) -> str:
    """Best-effort outcome for legacy receipts: exact match only, else
    'unknown'. Never substring matching."""
    r = str(result or "").strip().lower()
    if r == "success":
        return "success"
    if r == "failure":
        return "failure"
    return "unknown"


def from_legacy_olp(d: Dict[str, Any]) -> Dict[str, Any]:
    """openline-protocol scripts/olp.py format (olp_version 0.1)."""
    r = new_receipt(
        claim=d.get("claim", ""), action=d.get("action", ""),
        result=d.get("result", ""), tokens_used=d.get("tokens_used", 0),
        witness=d.get("witness", ""), next_use_note=d.get("next_use_note", ""),
        timestamp=d.get("timestamp"),
        outcome=legacy_outcome(d.get("result")),
    )
    r["receipt_id"] = d.get("receipt_id", r["receipt_id"])
    if d.get("evidence_hash"):
        r["evidence_hash"] = d["evidence_hash"]
    r["legacy"] = {
        "source": "openline-protocol/0.1",
        "signature_verified": False,
        "note": "source format carries no signature; "
                "integrity of converted payload is not cryptographically verifiable",
    }
    return r


def from_legacy_swarm(d: Dict[str, Any]) -> Dict[str, Any]:
    """epistemic-swarm OLPReceipt format (hard-coded olp_version 1.0)."""
    r = new_receipt(
        claim=d.get("claim", ""), action=d.get("action", ""),
        result=d.get("result", ""), tokens_used=d.get("tokens_used", 0),
        witness=d.get("witness", ""), next_use_note=d.get("next_use_note", ""),
        timestamp=d.get("timestamp"),
        outcome=legacy_outcome(d.get("result")),
    )
    r["receipt_id"] = d.get("receipt_id", r["receipt_id"])
    if d.get("evidence_hash"):
        r["evidence_hash"] = d["evidence_hash"]
    r["legacy"] = {
        "source": "epistemic-swarm/1.0",
        "signature_verified": False,
        "note": "source format carries no signature and no chain links; "
                "olp_version 1.0 was swarm-local and is retired",
    }
    return r


def from_legacy_adapter(d: Dict[str, Any]) -> Dict[str, Any]:
    """openline-proof-adapter generate_receipt.py format."""
    r = new_receipt(
        claim=d.get("claim", ""), action=d.get("action", ""),
        result=d.get("result", ""), tokens_used=d.get("tokens_used", 0),
        witness=d.get("witness", ""), next_use_note=d.get("next_use_note", ""),
        parent_hash=d.get("parent_hash"),
        timestamp=d.get("timestamp"),
        outcome=legacy_outcome(d.get("result")),
    )
    r["receipt_id"] = uuid.uuid4().hex  # adapter format has no receipt_id
    if d.get("evidence_hash"):
        r["evidence_hash"] = d["evidence_hash"]
    r["legacy"] = {
        "source": "openline-proof-adapter",
        "signature_verified": False,
        "note": "source 'signature' is a recomputable mock hash, not a "
                "cryptographic signature; parent_hash was caller-supplied "
                "and unverified",
    }
    return r


CONVERTERS = {
    "openline-protocol": from_legacy_olp,
    "epistemic-swarm": from_legacy_swarm,
    "openline-proof-adapter": from_legacy_adapter,
}
