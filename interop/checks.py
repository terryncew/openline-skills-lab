#!/usr/bin/env python3
"""One documented command that runs all interop checks.

    python -m interop.checks [--report PATH]

Runs the baseline problem reproduction (in an isolated sandbox) and the
full integration test suite, writes a JSON report, and exits nonzero if
anything fails.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
import unittest

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_baseline_repro():
    """Execute the actual baseline sources in an isolated sandbox."""
    script = os.path.join(LAB, "interop", "baseline_repro.py")
    if not os.path.exists(script):
        return {"status": "skipped", "detail": "baseline_repro.py not found"}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, script],
                          capture_output=True, text=True, cwd=LAB, env=env)
    try:
        with open(os.path.join(LAB, "interop", "baseline-repro.json")) as f:
            items = json.load(f)
    except OSError:
        items = []
    reproduced = sum(1 for i in items if i.get("status") == "REPRODUCED")
    return {"status": "done" if proc.returncode == 0 else "failed",
            "reproduced": reproduced, "total": len(items),
            "checks": items,
            "stdout_tail": proc.stdout[-2000:]}


def run_integration_tests():
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(LAB, "interop", "tests"),
                            pattern="test_*.py", top_level_dir=LAB)
    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=1)
    t0 = time.time()
    result = runner.run(suite)
    dt = time.time() - t0
    failures = [{"test": str(t), "error": e[-1500:]}
                for t, e in result.failures + result.errors]
    return {"status": "done" if result.wasSuccessful() else "failed",
            "tests_run": result.testsRun,
            "failures": failures,
            "errors": len(result.errors),
            "duration_s": round(dt, 2),
            "output_tail": buf.getvalue()[-2000:]}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run interop checks; write JSON report; "
                    "exit nonzero on failure.")
    ap.add_argument("--report",
                    default=os.path.join(LAB, "interop", "checks-report.json"),
                    help="where to write the JSON report")
    args = ap.parse_args()

    report = {"command": "python -m interop.checks",
              "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print("== baseline reproduction ==")
    report["baseline"] = run_baseline_repro()
    b = report["baseline"]
    print(f"baseline: {b.get('reproduced')}/{b.get('total')} problems "
          f"reproduced ({b.get('status')})")
    print("== integration tests ==")
    report["integration"] = run_integration_tests()
    ig = report["integration"]
    print(f"integration: {ig['tests_run']} tests, "
          f"{len(ig['failures'])} failures, {ig['errors']} errors "
          f"({ig['status']})")

    ok = (b.get("status") == "done"
          and ig["status"] == "done")
    # Baseline "done" means all 5 problems reproduced (exit 0 of repro).
    report["overall"] = "pass" if ok else "fail"
    with open(args.report, "w") as f:
        json.dump(report, f, indent=1)
    print(f"report written to {args.report}")
    print(f"OVERALL: {report['overall']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
