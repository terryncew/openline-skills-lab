"""Canonical JSON serialization and hashing.

One canonical form is used for every payload hash and signature in this
package. Changing this function invalidates all existing signatures.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON bytes: sorted keys, no whitespace."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_hash_of(mapping: dict) -> str:
    return sha256_hex(canonical(mapping))
