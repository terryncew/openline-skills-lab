"""Conversion checks: legacy formats -> unified schema, honest status."""
import unittest

from interop.schema import (CONVERTERS, OLP_VERSION, RECEIPT_SCHEMA_VERSION,
                            from_legacy_adapter, from_legacy_olp,
                            from_legacy_swarm, validate_shape)


def olp_receipt():
    return {"olp_version": "0.1", "receipt_id": "abc-123",
            "claim": "c", "action": "tool_call", "evidence_hash": "h",
            "result": "success", "tokens_used": 5,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "witness": "grok-agent", "next_use_note": "n"}


def swarm_receipt():
    return {"olp_version": "1.0", "receipt_id": "deadbeef01234567",
            "timestamp": "2026-01-01T00:00:00", "claim": "c",
            "action": "task_complete", "evidence_hash": "h",
            "result": "done", "tokens_used": 0,
            "witness": "epistemic-swarm", "next_use_note": "",
            "digest": {}}


def adapter_receipt():
    return {"claim": "c", "action": "tool_call", "evidence_hash": "h",
            "result": "success", "tokens_used": 42,
            "timestamp": "2026-01-01T00:00:00Z",
            "witness": "grok-openline-adapter", "parent_hash": "whatever",
            "next_use_note": "", "signature": "mockhash"}


class TestConverters(unittest.TestCase):
    def test_olp_converts(self):
        r = from_legacy_olp(olp_receipt())
        validate_shape(r)
        self.assertEqual(r["schema_version"], RECEIPT_SCHEMA_VERSION)
        self.assertEqual(r["olp_version"], OLP_VERSION)
        self.assertEqual(r["receipt_id"], "abc-123")  # id preserved
        self.assertEqual(r["evidence_hash"], "h")     # original hash kept
        self.assertEqual(r["outcome"], "success")     # exact "success"
        self.assertFalse(r["legacy"]["signature_verified"])
        self.assertIn("openline-protocol", r["legacy"]["source"])

    def test_swarm_converts(self):
        r = from_legacy_swarm(swarm_receipt())
        validate_shape(r)
        self.assertEqual(r["olp_version"], OLP_VERSION)  # 1.0 retired
        self.assertEqual(r["receipt_id"], "deadbeef01234567")
        self.assertEqual(r["outcome"], "unknown")  # "done" is not "success"
        self.assertFalse(r["legacy"]["signature_verified"])
        self.assertIn("1.0", r["legacy"]["note"])  # retirement noted

    def test_outcome_never_substring_matched(self):
        # "unsuccessful" must not become success; "not successful"
        # must not become success either.
        d = dict(olp_receipt(), result="unsuccessful")
        self.assertEqual(from_legacy_olp(d)["outcome"], "unknown")
        d = dict(olp_receipt(), result="not successful")
        self.assertEqual(from_legacy_olp(d)["outcome"], "unknown")
        d = dict(olp_receipt(), result="failure")
        self.assertEqual(from_legacy_olp(d)["outcome"], "failure")

    def test_adapter_converts(self):
        r = from_legacy_adapter(adapter_receipt())
        validate_shape(r)
        self.assertEqual(r["parent_hash"], "whatever")  # carried, not trusted
        self.assertFalse(r["legacy"]["signature_verified"])
        self.assertIn("mock", r["legacy"]["note"])

    def test_converters_cover_all_sources(self):
        self.assertEqual(set(CONVERTERS),
                         {"openline-protocol", "epistemic-swarm",
                          "openline-proof-adapter"})

    def test_converted_receipts_do_not_verify_as_signed(self):
        # Honest status: a converted receipt must never pass as signed.
        from interop.chain import Signer, verify_receipt
        signer = Signer.generate()
        pub = signer._key.public_key()
        for fn, src in ((from_legacy_olp, olp_receipt()),
                        (from_legacy_swarm, swarm_receipt()),
                        (from_legacy_adapter, adapter_receipt())):
            problems = verify_receipt(fn(src), pub)
            self.assertTrue(problems, f"{fn.__name__} verified?!")
            self.assertTrue(any("missing field" in p or "legacy" in p
                                for p in problems))


if __name__ == "__main__":
    unittest.main()
