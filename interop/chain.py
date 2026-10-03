"""Verifiable receipt chains: Ed25519 signatures + predecessor links.

- Canonical serialization (canonical.py) -> payload_hash (sha256).
- Ed25519 signature over the payload_hash bytes.
- parent_hash links each receipt to the previous receipt's payload_hash.
- Keys are configured OUTSIDE the repository via environment variables:
    OLP_LAB_SIGNING_KEY : 64-hex-char Ed25519 seed (private)
    OLP_LAB_PUBLIC_KEY  : 64-hex-char Ed25519 public key
  Never commit keys. Tests generate ephemeral keys.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .canonical import canonical, sha256_hex
from .schema import RECEIPT_SCHEMA_VERSION

SIGNING_KEY_ENV = "OLP_LAB_SIGNING_KEY"
PUBLIC_KEY_ENV = "OLP_LAB_PUBLIC_KEY"


def body_of(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """The signed payload: receipt content minus the signature envelope
    (signature, payload_hash, signer_pubkey). The hash covers the body,
    not itself and not its own metadata."""
    return {k: v for k, v in receipt.items()
            if k not in ("signature", "payload_hash", "signer_pubkey")}


def compute_payload_hash(receipt: Dict[str, Any]) -> str:
    return sha256_hex(canonical(body_of(receipt)))


class Signer:
    def __init__(self, private_key: Ed25519PrivateKey):
        self._key = private_key

    @classmethod
    def generate(cls) -> "Signer":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed_hex(cls, seed_hex: str) -> "Signer":
        seed = bytes.fromhex(seed_hex)
        if len(seed) != 32:
            raise ValueError("Ed25519 seed must be 32 bytes (64 hex chars)")
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    @classmethod
    def from_env(cls) -> "Signer":
        seed_hex = os.environ.get(SIGNING_KEY_ENV)
        if not seed_hex:
            raise RuntimeError(
                f"{SIGNING_KEY_ENV} is not set; signing keys live outside "
                "the repository")
        return cls.from_seed_hex(seed_hex)

    def public_key_hex(self) -> str:
        return self._key.public_key().public_bytes_raw().hex()

    def sign_payload_hash(self, payload_hash_hex: str) -> str:
        return self._key.sign(bytes.fromhex(payload_hash_hex)).hex()


def public_key_from_hex(pub_hex: str) -> Ed25519PublicKey:
    raw = bytes.fromhex(pub_hex)
    if len(raw) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes (64 hex chars)")
    return Ed25519PublicKey.from_public_bytes(raw)


def public_key_hex(public_key: Ed25519PublicKey) -> str:
    return public_key.public_bytes_raw().hex()


def public_key_from_env() -> Ed25519PublicKey:
    pub_hex = os.environ.get(PUBLIC_KEY_ENV)
    if not pub_hex:
        raise RuntimeError(f"{PUBLIC_KEY_ENV} is not set")
    return public_key_from_hex(pub_hex)


def sign_receipt(receipt: Dict[str, Any], signer: Signer,
                 parent_hash: Optional[str] = None) -> Dict[str, Any]:
    """Attach predecessor link, payload hash, and Ed25519 signature.

    Mutates and returns the receipt. The caller supplies parent_hash
    (normally storage.head()); genesis receipts use None.
    """
    receipt["parent_hash"] = parent_hash
    receipt["payload_hash"] = compute_payload_hash(receipt)
    receipt["signature"] = signer.sign_payload_hash(receipt["payload_hash"])
    receipt["signer_pubkey"] = signer.public_key_hex()
    return receipt


def verify_receipt(receipt: Dict[str, Any],
                   public_key: Ed25519PublicKey) -> List[str]:
    """Return a list of problems (empty = valid)."""
    problems: List[str] = []
    for f in ("payload_hash", "signature", "signer_pubkey"):
        if f not in receipt:
            problems.append(f"missing field: {f}")
    if problems:
        return problems
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        problems.append(
            f"unsupported schema_version: {receipt.get('schema_version')!r} "
            f"(expected {RECEIPT_SCHEMA_VERSION})")
        return problems
    if receipt.get("signer_pubkey") != public_key_hex(public_key):
        problems.append("signer_pubkey does not match the verifying key")
        return problems
    if receipt.get("legacy", {}).get("signature_verified") is False:
        problems.append("legacy receipt: no cryptographic signature to verify")
        return problems
    expected = compute_payload_hash(receipt)
    if receipt["payload_hash"] != expected:
        problems.append("payload_hash mismatch: payload was modified")
        return problems  # signature check is meaningless past this point
    try:
        public_key.verify(bytes.fromhex(receipt["signature"]),
                          bytes.fromhex(receipt["payload_hash"]))
    except (InvalidSignature, ValueError) as e:
        problems.append(f"signature invalid: {e}")
    return problems


@dataclass
class ChainResult:
    ok: bool
    failures: List[str] = field(default_factory=list)


def verify_chain(receipts: List[Dict[str, Any]],
                 public_key: Ed25519PublicKey) -> ChainResult:
    """Verify a receipt chain in order.

    Checks, per receipt: payload hash integrity, Ed25519 signature, and
    parent_hash continuity with the previous receipt. Reordered receipts
    break predecessor links and are rejected. Works from exported receipts
    + public key only (no storage access).
    """
    failures: List[str] = []
    if not receipts:
        return ChainResult(ok=True)  # vacuous: nothing to contradict
    prev_hash: Optional[str] = None
    for i, r in enumerate(receipts):
        rid = r.get("receipt_id", f"#{i}")
        for p in verify_receipt(r, public_key):
            failures.append(f"[{rid}] {p}")
        if r.get("parent_hash") != prev_hash:
            failures.append(
                f"[{rid}] broken predecessor link: parent_hash="
                f"{r.get('parent_hash')!r} != {prev_hash!r}")
        prev_hash = r.get("payload_hash")
    return ChainResult(ok=not failures, failures=failures)
