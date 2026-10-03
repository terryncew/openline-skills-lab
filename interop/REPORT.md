# Execution report — interop integration

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m interop.checks`
(also the CI workflow). JSON report: `interop/checks-report.json`.
Latest green run: **50 tests, 0 failures, 0 errors; 5/5 baseline
problems reproduced. OVERALL: pass.**

## Part 1 — baseline failures (reproduced from actual sources)

`interop/baseline_repro.py` executes the three unmodified baseline
packages against an isolated `/home/workdir` sandbox. 5/5 documented
problems reproduced:

| # | problem | observed |
|---|---|---|
| P1 | index shape conflict | OLP writes `{"receipts":..,"chain":..}` dict; swarm `.append()`s → `AttributeError: 'dict' object has no attribute 'append'`. Reverse order: OLP `index["receipts"]` on swarm's bare list → `TypeError: list indices must be integers or slices, not str` |
| P2 | divergent locations + versions | OLP → `receipts/<uuid>.json` (`olp_version 0.1`); swarm → `<16-hex>.json` flat under `.olp/` (`olp_version 1.0`) |
| P3 | adapter chain not maintained | `parent_hash="totally-unrelated"` accepted verbatim, never linked to previous receipt; `signature` is a recomputable mock hash |
| P4 | OWA always accepts | `orthogonal_witness_verify` returned `True` for a forged receipt with no checks |
| P5 | swarm never invokes COLE/controller; stale memory | `run_task` emitted to disk but `orchestrator.receipts` stayed at 0; `swarm.py` contains no reference to `cole_monitor`/`tc_controller` |

## Part 2 — integration results (50 tests, 0 failures)

| area | tests | result |
|---|---|---|
| storage: index normalization (missing/dict/list/invalid/**null rejected, file untouched**) | 5 | pass |
| storage: both baseline init orders converge | 2 | pass |
| storage: restart recovery | 1 | pass |
| storage: duplicate receipt_id rejected, history preserved | 1 | pass |
| storage: concurrent writes (8 threads × 25, no loss/dup) | 1 | pass |
| storage: **chain intact after concurrent writes (verify_chain over index order)** | 1 | pass |
| storage: handoff (fresh + populated) | 2 | pass |
| chain: canonical serialization vectors | 3 | pass |
| chain: sign/verify roundtrip, tampered payload, exported+pubkey | 3 | pass |
| chain: **wrong key → signer-key mismatch; tampered embedded key; unsupported schema** | 3 | pass |
| chain: verify_chain valid / broken link / reordered / missing | 4 | pass |
| conversion: 3 legacy formats + honest status + never-verifies-as-signed | 4 | pass |
| conversion: **outcome never substring-matched ("unsuccessful"→unknown)** | 1 | pass |
| conversion: converter registry covers all three sources | 1 | pass |
| orchestration: executor outcomes (success/exception), memory updated every emit | 3 | pass |
| orchestration: witness rejection propagates; chain_witness rejects tampering | 2 | pass |
| orchestration: COLE+controller invoked; controller boundaries; drift→reroute; no reroute when healthy; epsilon metric | 5 | pass |
| orchestration: **substring traps ("unsuccessful"/"not successful") can't be last_good** | 1 | pass |
| orchestration: restart rebuilds memory; cross-restart chain verifies | 1 | pass |
| orchestration: **reroute survives restart (fallback used after)** | 1 | pass |
| orchestration: **concurrent tasks keep a verifiable chain** | 1 | pass |
| orchestration: concurrent cold baseline imports restore patched globals | 1 | pass |
| isolation: no import-time filesystem writes; storage writes stay in root | 2 | pass |
| repro safety: **sentinel files survive the baseline reproduction** | 1 | pass |

Exit code: 0 on this run; verified 1 on forced failure.

## Notes

- Baseline `.pyc` caches restored byte-for-byte after reproduction runs
  (`git status` shows no baseline modifications); `PYTHONDONTWRITEBYTECODE=1`
  is used for all runs touching baseline sources.
- No real user receipt store was touched: baseline ran in `/home/workdir`
  sandbox (cleaned after), integration tests use temp dirs; the default
  `~/.olp-skills-lab` was never created by the test suite.
- Runtime validation is complete (not pending): everything above executed
  on this machine.
