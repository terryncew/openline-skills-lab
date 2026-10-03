"""Shared test helpers: ephemeral keys, temp storage, signed receipts."""
import tempfile

from interop.chain import Signer
from interop.schema import new_receipt
from interop.storage import Storage


def make_signer():
    return Signer.generate()


def make_storage():
    tmp = tempfile.mkdtemp(prefix="olp-lab-test-")
    return Storage(tmp), tmp


def signed_emit(storage, signer, claim="c", action="a", result="success",
                **kw):
    """Emit via the atomic sign+append transaction (the real path)."""
    def build(parent):
        return new_receipt(claim=claim, action=action, result=result,
                           parent_hash=parent, **kw)
    return storage.emit_signed(build, signer)
