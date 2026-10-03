"""Orchestration checks: executor outcomes, witnesses, COLE/controller."""
import builtins
import os
import threading
import unittest

from interop import baseline_shim
from interop.chain import Signer
from interop.orchestrate import (Orchestrator, WitnessResult, chain_witness,
                                 drift_epsilon)
from interop.storage import Storage
from .helpers import make_storage


def make_orch(tmp=None, **kw):
    s = Storage(tmp) if tmp else make_storage()[0]
    signer = Signer.generate()
    kw.setdefault("witnesses", [chain_witness])
    return Orchestrator(s, signer, signer.public_key_hex(), **kw), s, signer


def ok_executor(task):
    return {"result": "success: did " + task, "evidence": {"n": 1},
            "tokens_used": 7}


def fail_executor(task):
    return {"result": "failure: broke " + task, "evidence": {},
            "tokens_used": 3, "outcome": "failure"}


def boom_executor(task):
    raise RuntimeError("executor exploded")


class TestExecutorOutcomes(unittest.TestCase):
    def test_success_recorded(self):
        orch, s, _ = make_orch()
        out = orch.run_task("t1", ok_executor)
        self.assertTrue(out["accepted"])
        done = out["receipt"]
        self.assertIn("success", done["result"])
        self.assertEqual(done["tokens_used"], 7)

    def test_exception_becomes_failure_receipt(self):
        orch, s, _ = make_orch()
        out = orch.run_task("t2", boom_executor)
        done = out["receipt"]
        self.assertIn("failure", done["result"])
        self.assertIn("exploded", done["result"])

    def test_in_memory_state_updated_every_emit(self):
        orch, s, _ = make_orch()
        orch.run_task("t3", ok_executor)
        # start + complete + witness_verdicts + drift_check = 4 receipts
        self.assertEqual(len(orch.receipts), 4)
        self.assertEqual(s.count(), 4)
        self.assertEqual(
            [r["receipt_id"] for r in orch.receipts], s.list_ids())


class TestWitnesses(unittest.TestCase):
    def test_rejecting_witness_propagates(self):
        def bad_witness(receipt, pubkey):
            return WitnessResult(witness="skeptic", ok=False,
                                 detail="nope")
        orch, s, _ = make_orch(witnesses=[bad_witness])
        out = orch.run_task("t4", ok_executor)
        self.assertFalse(out["accepted"])
        kinds = [r["action"] for r in orch.receipts]
        self.assertIn("witness_verdicts", kinds)
        v = next(r for r in orch.receipts
                 if r["action"] == "witness_verdicts")
        self.assertEqual(v["result"], "rejected")

    def test_chain_witness_is_real(self):
        # chain_witness must reject a tampered receipt, unlike baseline OWA.
        orch, s, signer = make_orch()
        out = orch.run_task("t5", ok_executor)
        done = out["receipt"]
        self.assertTrue(chain_witness(done, orch.public_key).ok)
        tampered = dict(done, result="success (forged)")
        self.assertFalse(chain_witness(tampered, orch.public_key).ok)


class TestColeAndController(unittest.TestCase):
    def test_concurrent_cold_baseline_imports_restore_globals(self):
        baseline_shim._cache.clear()
        real_print = builtins.print
        real_makedirs = os.makedirs
        errors = []
        barrier = threading.Barrier(3)

        def load(loader):
            try:
                barrier.wait()
                loader()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=load, args=(loader,))
                   for loader in (baseline_shim.cole, baseline_shim.terrynce,
                                  baseline_shim.owa)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertIs(builtins.print, real_print)
        self.assertIs(os.makedirs, real_makedirs)
        self.assertEqual(set(baseline_shim._cache), {"cole", "terrynce", "owa"})

    def test_baseline_cole_and_controller_invoked(self):
        orch, s, _ = make_orch()
        out = orch.run_task("t6", ok_executor)
        self.assertIn("stress_kappa", out["cole"])
        self.assertIn("noise_epsilon", out["cole"])
        kinds = [r["action"] for r in orch.receipts]
        self.assertIn("drift_check", kinds)

    def test_controller_boundaries(self):
        # Baseline controller, real thresholds.
        last = {"receipt_id": "g"}
        cont = baseline_shim.tc_controller(0.1, "general", last)
        self.assertEqual(cont["action"], "continue")
        over = baseline_shim.tc_controller(0.9, "general", last)
        self.assertEqual(over["action"], "reroute")
        self.assertEqual(over["last_good"], "g")

    def test_drift_triggers_reroute(self):
        used = []

        def primary(task):
            used.append("primary")
            return {"result": "failure", "evidence": {}, "tokens_used": 1,
                    "outcome": "failure"}

        def fallback(task):
            used.append("fallback")
            return {"result": "success", "evidence": {}, "tokens_used": 1}

        orch, s, _ = make_orch(fallback_executor=fallback)
        # Enough consecutive failures to push drift_epsilon over 0.45.
        for i in range(6):
            orch.run_task(f"drift-{i}", primary)
        kinds = [r["action"] for r in orch.receipts]
        self.assertIn("reroute", kinds)
        # After reroute, the fallback executor is used.
        used.clear()
        orch.run_task("after", primary)
        self.assertIn("fallback", used)
        self.assertNotIn("primary", used)

    def test_no_reroute_when_healthy(self):
        orch, s, _ = make_orch(fallback_executor=lambda t: {})
        for i in range(4):
            out = orch.run_task(f"ok-{i}", ok_executor)
            self.assertFalse(out["rerouted"])
        kinds = [r["action"] for r in orch.receipts]
        self.assertNotIn("reroute", kinds)

    def test_drift_epsilon_compatible(self):
        recs = [{"action": "task_complete", "result": "success",
                 "outcome": "success"}] * 6
        self.assertEqual(drift_epsilon(recs), 0.0)
        recs = ([{"action": "task_complete", "result": "success",
                  "outcome": "success"}] * 5
                + [{"action": "task_complete", "result": "failure",
                    "outcome": "failure"}] * 5)
        self.assertEqual(drift_epsilon(recs), 0.5)

    def test_substring_traps_do_not_count_as_success(self):
        # "unsuccessful" contains "success"; "not successful" contains
        # "successful". With explicit outcomes neither reads as success,
        # and neither can become last_good.
        orch, s, _ = make_orch()
        orch.run_task("trap1", lambda t: {"result": "unsuccessful",
                                          "outcome": "failure"})
        orch.run_task("trap2", lambda t: {"result": "not successful",
                                          "outcome": "failure"})
        self.assertEqual(drift_epsilon(orch.receipts), 1.0)
        self.assertIsNone(orch._last_good())
        # ...but an explicit success outcome is honored even with odd text.
        orch.run_task("trap3", lambda t: {"result": "done?",
                                          "outcome": "success"})
        self.assertIsNotNone(orch._last_good())
        self.assertEqual(orch._last_good()["claim"], "Task result: trap3")


class TestRestartRecoveryOrchestrator(unittest.TestCase):
    def test_orchestrator_rebuilds_memory(self):
        import tempfile
        from interop.chain import verify_chain
        tmp = tempfile.mkdtemp(prefix="olp-lab-orch-")
        orch, s, signer = make_orch(tmp)
        orch.run_task("t7", ok_executor)
        n = len(orch.receipts)
        head_before = s.head()
        orch2 = Orchestrator(s, signer, signer.public_key_hex())
        self.assertEqual(len(orch2.receipts), n)
        orch2.run_task("t8", ok_executor)
        # the first receipt after restart links to the stored head ...
        first_new = orch2.receipts[n]
        self.assertEqual(first_new["parent_hash"], head_before)
        # ... and the full cross-restart chain verifies.
        pub = signer._key.public_key()
        res = verify_chain(orch2.receipts, pub)
        self.assertTrue(res.ok, res.failures)


    def test_reroute_survives_restart(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="olp-lab-reroute-")
        used = []

        def primary(task):
            used.append("primary")
            return {"result": "failure", "evidence": {}, "tokens_used": 1,
                    "outcome": "failure"}

        def fallback(task):
            used.append("fallback")
            return {"result": "success", "evidence": {}, "tokens_used": 1}

        orch, s, signer = make_orch(tmp, fallback_executor=fallback)
        for i in range(6):
            orch.run_task(f"drift-{i}", primary)
        self.assertTrue(orch.rerouted)
        # restart: routing decision restored from receipts; fallback
        # callable re-supplied (callables cannot be persisted).
        orch2 = Orchestrator(Storage(tmp), signer, signer.public_key_hex(),
                             fallback_executor=fallback)
        self.assertTrue(orch2.rerouted)
        used.clear()
        orch2.run_task("after-restart", primary)
        self.assertIn("fallback", used)
        self.assertNotIn("primary", used)

    def test_concurrent_tasks_keep_chain(self):
        import threading
        from interop.chain import verify_chain
        orch, s, signer = make_orch()
        errors = []

        def worker(t):
            try:
                orch.run_task(f"conc-{t}", ok_executor)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        receipts = [s.load(rid) for rid in s.list_ids()]
        res = verify_chain(receipts, signer._key.public_key())
        self.assertTrue(res.ok, res.failures[:5])


if __name__ == "__main__":
    unittest.main()
