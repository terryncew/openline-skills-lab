"""Isolation: importing interop (incl. baseline shim) must not write
to the filesystem outside explicitly provided storage roots."""
import os
import subprocess
import sys
import unittest


class TestImportIsolation(unittest.TestCase):
    def test_no_import_time_writes(self):
        code = (
            "import os, sys; "
            "calls = []; "
            "real = os.makedirs; "
            "os.makedirs = lambda *a, **k: calls.append(a[0] if a else None); "
            "import interop.baseline_shim as shim; "
            "shim.cole(); shim.terrynce(); shim.owa(); "
            "import interop.orchestrate, interop.storage, interop.chain; "
            "print('MAKEDIRS_CALLS:' + repr(calls))"
        )
        here = os.path.abspath(__file__)  # .../lab/interop/tests/...
        lab = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        env = dict(os.environ,
                   PYTHONPATH=lab + os.pathsep + os.environ.get("PYTHONPATH", ""),
                   PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, cwd="/tmp", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        line = next(l for l in proc.stdout.splitlines()
                    if l.startswith("MAKEDIRS_CALLS:"))
        self.assertEqual(line, "MAKEDIRS_CALLS:[]",
                         f"import-time makedirs calls detected: {line}")

    def test_storage_only_writes_inside_root(self):
        import tempfile
        from interop.storage import Storage
        tmp = tempfile.mkdtemp(prefix="olp-lab-root-")
        before = set(os.listdir("/tmp"))
        Storage(tmp)
        after = set(os.listdir("/tmp"))
        # Only our own temp dir may exist; nothing else new at /tmp level.
        self.assertTrue(set(after) - set(before) <= {os.path.basename(tmp)})


if __name__ == "__main__":
    unittest.main()
