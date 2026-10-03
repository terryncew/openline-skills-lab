"""Repro-safety: the baseline reproduction must never delete existing
stores. Plants sentinel files at the hard-coded sandbox paths, runs the
repro as a subprocess, and asserts the sentinels survive byte-for-byte."""
import json
import os
import subprocess
import sys
import unittest

LAB = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

SENTINELS = {
    "/home/workdir/.olp": ("SENTINEL_OLP", "do-not-delete-olp"),
    "/home/workdir/.openline": ("SENTINEL_ADAPTER", "do-not-delete-adapter"),
}


class TestReproSafety(unittest.TestCase):
    def test_sentinel_files_survive_repro(self):
        created = []
        try:
            for d, (name, content) in SENTINELS.items():
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, name)
                with open(p, "w") as f:
                    f.write(content)
                created.append(p)
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            command = [sys.executable, os.path.join(
                LAB, "interop", "baseline_repro.py")]
            # Start two cold reproductions together. Their hard-coded stores
            # must be protected for the full stash/run/restore lifecycle.
            procs = [subprocess.Popen(command, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True,
                                      cwd=LAB, env=env)
                     for _ in range(2)]
            for proc in procs:
                _, stderr = proc.communicate(timeout=60)
                self.assertEqual(proc.returncode, 0, stderr[-1000:])
            with open(os.path.join(
                    LAB, "interop", "baseline-repro.json")) as report_file:
                report = json.load(report_file)
            reproduced = sum(1 for i in report
                             if i.get("status") == "REPRODUCED")
            self.assertEqual(reproduced, 5)
            for d, (name, content) in SENTINELS.items():
                p = os.path.join(d, name)
                self.assertTrue(os.path.exists(p),
                                f"sentinel deleted: {p}")
                with open(p) as f:
                    self.assertEqual(f.read(), content)
        finally:
            for d, (name, _) in SENTINELS.items():
                try:
                    os.remove(os.path.join(d, name))
                except OSError:
                    pass
            for d in SENTINELS:
                try:
                    os.rmdir(d)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
