"""Shared receipt storage: one directory, one index, many callers.

Layout:
    <root>/receipts/<receipt_id>.json
    <root>/index.json  -> {"format": "olp-skills-lab/index-1",
                          "receipts": [<ids in emission order>],
                          "head": <payload_hash of last receipt | None>}
    <root>/index.lock  -> lock file (never replaced; guards read-modify-write)

The index loader is the single canonical reader. It accepts:
  - missing file            -> fresh empty index
  - bare list (legacy swarm)-> normalized to dict (ids only, head=None)
  - dict with "receipts"    -> canonical form (protocol or ours)
  - anything else           -> fail closed with ValueError

Writes are atomic (temp file + os.replace) and serialized with an
in-process lock plus fcntl.flock on a dedicated lock file for
cross-process safety, so concurrent emits cannot lose receipts.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

INDEX_FORMAT = "olp-skills-lab/index-1"
DEFAULT_ROOT = os.path.expanduser("~/.olp-skills-lab")
ROOT_ENV = "OLP_LAB_DIR"


def default_root() -> str:
    return os.environ.get(ROOT_ENV, DEFAULT_ROOT)


class StorageError(RuntimeError):
    pass


_MISSING = object()  # sentinel: index file absent (distinct from JSON null)


def normalize_index(raw: Any) -> Dict[str, Any]:
    """Canonicalize any supported index shape. Fail closed otherwise.

    A missing file yields a fresh index. An explicit JSON null is NOT a
    missing file -- it is rejected without touching the file, so no
    caller can silently reset existing state.
    """
    if raw is _MISSING:
        return {"format": INDEX_FORMAT, "receipts": [], "head": None}
    if isinstance(raw, list):
        # Legacy swarm bare-list format.
        return {"format": INDEX_FORMAT, "receipts": list(raw), "head": None}
    if isinstance(raw, dict):
        receipts = raw.get("receipts")
        if isinstance(receipts, list):
            return {"format": INDEX_FORMAT,
                    "receipts": list(receipts),
                    "head": raw.get("head")}
        # Protocol dict without a receipts list is not usable.
        raise StorageError(
            f"unsupported index dict shape: keys={sorted(raw.keys())}")
    raise StorageError(f"unsupported index type: {type(raw).__name__}")


class Storage:
    def __init__(self, root: Optional[str] = None):
        self.root = Path(root or default_root())
        self.receipts_dir = self.root / "receipts"
        self.index_path = self.root / "index.json"
        self._lock = threading.RLock()
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        # Validate (and normalize legacy shapes of) the index on open.
        with self._locked_index():
            pass

    @contextmanager
    def _locked_index(self) -> Iterator[Dict[str, Any]]:
        """Yield the on-disk index dict, holding an exclusive lock.

        A dedicated lock file (never replaced) guards the whole
        read-modify-write so concurrent processes cannot lose updates.
        Changes are written back atomically via temp file + os.replace.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / "index.lock"
        with self._lock:
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    with open(self.index_path, encoding="utf-8") as f:
                        raw = json.load(f)
                except FileNotFoundError:
                    raw = _MISSING
                except json.JSONDecodeError as e:
                    raise StorageError(f"index.json corrupt: {e}")
                index = normalize_index(raw)
                yield index
                tmp = self.index_path.with_suffix(".json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(index, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.index_path)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    # -- reads -----------------------------------------------------------
    def list_ids(self) -> List[str]:
        with self._locked_index() as index:
            return list(index["receipts"])

    def load(self, receipt_id: str) -> Dict[str, Any]:
        path = self.receipts_dir / f"{receipt_id}.json"
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise StorageError(f"receipt not found: {receipt_id}")
        except json.JSONDecodeError as e:
            raise StorageError(f"receipt {receipt_id} corrupt: {e}")

    def head(self) -> Optional[str]:
        with self._locked_index() as index:
            return index.get("head")

    def count(self) -> int:
        return len(self.list_ids())

    # -- writes ----------------------------------------------------------
    @staticmethod
    def _persist_receipt_file(receipts_dir: Path,
                              receipt: Dict[str, Any]) -> None:
        rid = receipt.get("receipt_id")
        if not rid:
            raise StorageError("receipt has no receipt_id")
        path = receipts_dir / f"{rid}.json"
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def emit(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a (signed) receipt and append it to the index.

        Returns the receipt. The receipt file is written before the index
        is updated, so a crash between the two can only orphan a file,
        never reference a missing one.
        """
        rid = receipt.get("receipt_id")
        if not rid:
            raise StorageError("receipt has no receipt_id")
        with self._locked_index() as index:
            if (rid in index["receipts"] or
                    (self.receipts_dir / f"{rid}.json").exists()):
                raise StorageError(f"duplicate receipt_id: {rid}")
            self._persist_receipt_file(self.receipts_dir, receipt)
            index["receipts"].append(rid)
            if receipt.get("payload_hash"):
                index["head"] = receipt["payload_hash"]
        return receipt

    def emit_signed(self, build, signer) -> Dict[str, Any]:
        """Build, sign, and persist a receipt as ONE transaction.

        `build(parent_hash)` returns the unsigned receipt. Head selection,
        signing, and the index append all happen under the same exclusive
        lock, so concurrent writers can never sign against the same
        predecessor -- the on-disk chain cannot fork.
        """
        # Local import to keep storage free of signing-dependency cycles.
        from .chain import sign_receipt
        with self._locked_index() as index:
            parent = index.get("head")
            receipt = build(parent)
            sign_receipt(receipt, signer, parent_hash=parent)
            rid = receipt.get("receipt_id")
            if not rid:
                raise StorageError("built receipt has no receipt_id")
            if (rid in index["receipts"] or
                    (self.receipts_dir / f"{rid}.json").exists()):
                raise StorageError(f"duplicate receipt_id: {rid}")
            self._persist_receipt_file(self.receipts_dir, receipt)
            index["receipts"].append(rid)
            index["head"] = receipt["payload_hash"]
        return receipt

    # -- handoff ---------------------------------------------------------
    def handoff_summary(self, limit: int = 10) -> Dict[str, Any]:
        """Portable handoff state. Safe on a fresh (empty) store."""
        ids = self.list_ids()
        recent = []
        for rid in ids[-limit:]:
            try:
                r = self.load(rid)
            except StorageError:
                continue
            recent.append({k: r.get(k) for k in
                           ("receipt_id", "claim", "action", "result",
                            "timestamp", "witness", "parent_hash",
                            "payload_hash")})
        digest = {
            "claim_hash": hashlib.sha256(
                "".join(r.get("claim", "") for r in recent)
                .encode()).hexdigest()[:8] if recent else "",
            "state_id": len(ids),
            "last_ts": recent[-1]["timestamp"] if recent else None,
        }
        return {"schema": "olp-skills-lab/handoff-1", "count": len(ids),
                "head": self.head(), "recent": recent, "digest": digest}
