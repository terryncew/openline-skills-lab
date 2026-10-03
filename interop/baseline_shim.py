"""Safe access to the baseline skill modules.

Two baseline modules perform filesystem writes at import time
(swarm.py: os.makedirs("/home/workdir/.olp");
generate_receipt.py: os.makedirs("/home/workdir/.openline")),
and all of them print at import. This shim imports them with those side
effects neutralized, so the integration and its tests never touch
existing user state at import time.

Only the pure logic is re-exported (cole_monitor, tc_controller,
thresholds). The baseline persistence paths are NOT used.
"""
from __future__ import annotations

import builtins
import importlib.util
import os
import threading
from pathlib import Path
from types import ModuleType
from typing import Dict

_LAB = Path(__file__).resolve().parent.parent
_BASELINES = {
    "cole": _LAB / "epistemic-swarm" / "scripts" / "cole.py",
    "terrynce": _LAB / "epistemic-swarm" / "scripts" / "terrynce.py",
    "owa": _LAB / "epistemic-swarm" / "scripts" / "owa.py",
}

_cache: Dict[str, ModuleType] = {}
_load_lock = threading.RLock()


def _load_safely(name: str, path: Path) -> ModuleType:
    """Import a baseline module with makedirs/print neutralized."""
    # The patches below affect process-wide functions. Keep the cache check,
    # import, restoration, and cache update in one critical section so a
    # second cold import cannot save one of our temporary replacements as the
    # function it later "restores".
    with _load_lock:
        if name in _cache:
            return _cache[name]
        real_makedirs = os.makedirs
        real_print = builtins.print

        def no_makedirs(*a, **k):
            return None

        def no_print(*a, **k):
            return None

        os.makedirs = no_makedirs  # type: ignore[assignment]
        builtins.print = no_print  # type: ignore[assignment]
        try:
            spec = importlib.util.spec_from_file_location(
                f"interop_baseline_{name}", path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            os.makedirs = real_makedirs  # type: ignore[assignment]
            builtins.print = real_print  # type: ignore[assignment]
        _cache[name] = mod
        return mod


def cole():
    return _load_safely("cole", _BASELINES["cole"])


def terrynce():
    return _load_safely("terrynce", _BASELINES["terrynce"])


def owa():
    return _load_safely("owa", _BASELINES["owa"])


def cole_monitor(receipts):
    """Baseline COLE coherence observation (pure)."""
    return cole().cole_monitor(receipts)


def terrynce_threshold(domain: str = "general") -> float:
    """Baseline Terrynce Curve threshold for a domain (pure)."""
    return terrynce().get_terrynce_threshold(domain)


def tc_controller(noise_e: float, domain: str, last_good_receipt):
    """Baseline graceful-failure controller (pure)."""
    return terrynce().tc_controller(noise_e, domain, last_good_receipt)
