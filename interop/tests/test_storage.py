"""Storage checks: init orders, restart recovery, concurrency, handoff."""
import json
import os
import threading
import unittest

from interop.storage import Storage, StorageError, normalize_index
from .helpers import make_signer, make_storage, signed_emit


class TestIndexNormalization(unittest.TestCase):
    def test_missing_file_gives_empty_index(self):
        s, _ = make_storage()
        self.assertEqual(s.list_ids(), [])
        self.assertIsNone(s.head())

    def test_canonical_dict_loads(self):
        s, tmp = make_storage()
        with open(os.path.join(tmp, "index.json"), "w") as f:
            json.dump({"receipts": ["a", "b"], "chain": []}, f)
        s2 = Storage(tmp)  # protocol-style dict normalizes
        self.assertEqual(s2.list_ids(), ["a", "b"])

    def test_bare_list_normalizes(self):
        s, tmp = make_storage()
        with open(os.path.join(tmp, "index.json"), "w") as f:
            json.dump(["x", "y"], f)  # legacy swarm shape
        s2 = Storage(tmp)
        self.assertEqual(s2.list_ids(), ["x", "y"])
        # normalized back to dict on disk
        with open(os.path.join(tmp, "index.json")) as f:
            self.assertIsInstance(json.load(f), dict)

    def test_invalid_type_fails_closed(self):
        with self.assertRaises(StorageError):
            normalize_index("nope")
        with self.assertRaises(StorageError):
            normalize_index(42)
        with self.assertRaises(StorageError):
            normalize_index({"no_receipts_key": 1})

    def test_json_null_rejected_without_modifying_file(self):
        _, tmp = make_storage()
        index_path = os.path.join(tmp, "index.json")
        with open(index_path, "w") as f:
            f.write("null")
        with self.assertRaises(StorageError):
            Storage(tmp)
        # file untouched: still exactly "null", not reset to empty index
        with open(index_path) as f:
            self.assertEqual(f.read(), "null")


class TestInitOrders(unittest.TestCase):
    """Both baseline initialization orders must converge on one store."""

    def _seed(self, tmp, payload):
        os.makedirs(os.path.join(tmp, "receipts"), exist_ok=True)
        with open(os.path.join(tmp, "index.json"), "w") as f:
            json.dump(payload, f)

    def test_protocol_first_then_swarm_shape(self):
        # protocol dict index, then a swarm-style bare list appears
        s, tmp = make_storage()
        self._seed(tmp, {"receipts": ["r1"], "chain": []})
        self.assertEqual(Storage(tmp).list_ids(), ["r1"])
        self._seed(tmp, ["r1", "r2"])
        self.assertEqual(Storage(tmp).list_ids(), ["r1", "r2"])

    def test_swarm_first_then_protocol_shape(self):
        s, tmp = make_storage()
        self._seed(tmp, ["r1"])
        self.assertEqual(Storage(tmp).list_ids(), ["r1"])
        self._seed(tmp, {"receipts": ["r1", "r2"], "chain": []})
        self.assertEqual(Storage(tmp).list_ids(), ["r1", "r2"])


class TestRestartRecovery(unittest.TestCase):
    def test_state_survives_restart(self):
        signer = make_signer()
        s, tmp = make_storage()
        ids = [signed_emit(s, signer, claim=f"c{i}")["receipt_id"]
               for i in range(5)]
        head = s.head()
        s2 = Storage(tmp)  # new instance = restart
        self.assertEqual(s2.list_ids(), ids)
        self.assertEqual(s2.head(), head)
        r = s2.load(ids[2])
        self.assertEqual(r["claim"], "c2")

    def test_duplicate_receipt_id_preserves_history(self):
        signer = make_signer()
        s, _ = make_storage()
        original = signed_emit(s, signer, claim="original")
        original_id = original["receipt_id"]
        original_head = s.head()

        def duplicate(parent):
            return {"receipt_id": original_id, "claim": "replacement",
                    "action": "test", "result": "success",
                    "outcome": "success", "evidence": {},
                    "tokens_used": 0}

        with self.assertRaisesRegex(StorageError, "duplicate receipt_id"):
            s.emit_signed(duplicate, signer)

        self.assertEqual(s.load(original_id), original)
        self.assertEqual(s.list_ids(), [original_id])
        self.assertEqual(s.count(), 1)
        self.assertEqual(s.head(), original_head)


class TestConcurrentWrites(unittest.TestCase):
    def test_no_lost_receipts(self):
        signer = make_signer()
        s, tmp = make_storage()
        n_threads, per = 8, 25
        errors = []

        def worker(t):
            try:
                for i in range(per):
                    signed_emit(s, signer, claim=f"t{t}-{i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        ids = s.list_ids()
        self.assertEqual(len(ids), n_threads * per)
        self.assertEqual(len(set(ids)), n_threads * per)

    def test_chain_intact_after_concurrent_writes(self):
        """Concurrent signers must not fork the chain: index order must
        verify end-to-end (each receipt's parent is the previous head)."""
        from interop.chain import verify_chain
        signer = make_signer()
        pub = signer._key.public_key()
        s, tmp = make_storage()
        n_threads, per = 8, 10
        errors = []

        def worker(t):
            try:
                for i in range(per):
                    signed_emit(s, signer, claim=f"c{t}-{i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        receipts = [s.load(rid) for rid in s.list_ids()]
        self.assertEqual(len(receipts), n_threads * per)
        res = verify_chain(receipts, pub)
        self.assertTrue(res.ok, res.failures[:5])


class TestHandoff(unittest.TestCase):
    def test_fresh_handoff_state(self):
        s, _ = make_storage()
        h = s.handoff_summary()
        self.assertEqual(h["count"], 0)
        self.assertIsNone(h["head"])
        self.assertEqual(h["recent"], [])

    def test_handoff_reflects_emits(self):
        signer = make_signer()
        s, _ = make_storage()
        signed_emit(s, signer, claim="hello")
        h = s.handoff_summary()
        self.assertEqual(h["count"], 1)
        self.assertEqual(h["head"], s.head())
        self.assertEqual(h["recent"][0]["claim"], "hello")


if __name__ == "__main__":
    unittest.main()
