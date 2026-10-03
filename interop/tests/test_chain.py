"""Chain checks: serialization vectors, sign/verify, tamper resistance."""
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey)

from interop.canonical import canonical, sha256_hex
from interop.chain import (Signer, compute_payload_hash, public_key_from_hex,
                           sign_receipt, verify_chain, verify_receipt)
from interop.schema import new_receipt


def build_chain(signer, n=4):
    receipts = []
    parent = None
    for i in range(n):
        r = new_receipt(claim=f"c{i}", action="a", result="success")
        sign_receipt(r, signer, parent_hash=parent)
        parent = r["payload_hash"]
        receipts.append(r)
    return receipts


class TestSerializationVectors(unittest.TestCase):
    def test_canonical_is_deterministic(self):
        self.assertEqual(canonical({"b": 1, "a": 2}), b'{"a":2,"b":1}')
        self.assertEqual(canonical({"b": 1, "a": 2}),
                         canonical({"a": 2, "b": 1}))

    def test_canonical_nested(self):
        self.assertEqual(
            canonical({"z": [3, 2], "a": {"y": 1, "x": 0}}),
            b'{"a":{"x":0,"y":1},"z":[3,2]}')

    def test_sha256_vector(self):
        # sha256 of empty string, well-known.
        self.assertEqual(sha256_hex(b""),
                         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


class TestSignVerify(unittest.TestCase):
    def test_roundtrip(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        r = new_receipt(claim="c", action="a", result="success")
        sign_receipt(r, signer)
        self.assertEqual(verify_receipt(r, pub), [])

    def test_tampered_payload_rejected(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        r = new_receipt(claim="c", action="a", result="success")
        sign_receipt(r, signer)
        r["result"] = "success (tampered)"
        problems = verify_receipt(r, pub)
        self.assertTrue(any("modified" in p for p in problems))

    def test_wrong_key_rejected(self):
        signer = Signer.generate()
        other = Ed25519PrivateKey.generate().public_key()
        r = new_receipt(claim="c", action="a", result="success")
        sign_receipt(r, signer)
        problems = verify_receipt(r, other)
        self.assertTrue(any("does not match the verifying key" in p
                            for p in problems))

    def test_tampered_signer_pubkey_rejected(self):
        # Attacker swaps the embedded key to their own: the signature
        # itself must still fail.
        signer = Signer.generate()
        attacker = Signer.generate()
        r = new_receipt(claim="c", action="a", result="success")
        sign_receipt(r, signer)
        r["signer_pubkey"] = attacker.public_key_hex()
        problems = verify_receipt(r, attacker._key.public_key())
        self.assertTrue(any("signature invalid" in p for p in problems))

    def test_unsupported_schema_rejected(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        r = new_receipt(claim="c", action="a", result="success")
        sign_receipt(r, signer)
        r["schema_version"] = 999
        # re-sign so only the schema check trips
        r.pop("signature")
        sign_receipt(r, signer, parent_hash=r["parent_hash"])
        problems = verify_receipt(r, pub)
        self.assertTrue(any("unsupported schema_version" in p
                            for p in problems))

    def test_verify_from_exported_json_plus_pubkey(self):
        signer = Signer.generate()
        pub_hex = signer.public_key_hex()
        r = new_receipt(claim="c", action="a", result="success")
        sign_receipt(r, signer)
        exported = json.loads(json.dumps(r))  # round-trip through JSON
        pub = public_key_from_hex(pub_hex)
        self.assertEqual(verify_receipt(exported, pub), [])
        res = verify_chain(exported if isinstance(exported, list) else [exported], pub)
        self.assertTrue(res.ok)


class TestVerifyChain(unittest.TestCase):
    def test_valid_chain(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        receipts = build_chain(signer, 4)
        res = verify_chain(receipts, pub)
        self.assertTrue(res.ok, res.failures)

    def test_broken_link_rejected(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        receipts = build_chain(signer, 3)
        receipts[2]["parent_hash"] = "0" * 64
        # re-sign so the signature itself is valid; only the link is broken
        receipts[2].pop("signature")
        sign_receipt(receipts[2], signer, parent_hash="0" * 64)
        res = verify_chain(receipts, pub)
        self.assertFalse(res.ok)
        self.assertTrue(any("predecessor link" in f for f in res.failures))

    def test_reordered_rejected(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        receipts = build_chain(signer, 3)
        receipts[1], receipts[2] = receipts[2], receipts[1]
        res = verify_chain(receipts, pub)
        self.assertFalse(res.ok)

    def test_missing_link_rejected(self):
        signer = Signer.generate()
        pub = signer._key.public_key()
        receipts = build_chain(signer, 3)
        del receipts[1:]  # drop tail; then tamper middle link target
        receipts = build_chain(signer, 3)
        receipts.pop(1)  # remove middle receipt -> link from 2 to 0 breaks
        res = verify_chain(receipts, pub)
        self.assertFalse(res.ok)


if __name__ == "__main__":
    unittest.main()
