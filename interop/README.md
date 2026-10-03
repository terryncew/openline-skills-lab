# interop/ — tested integration for the three local skills

One versioned receipt schema, one storage layer, verifiable chains, and
working orchestration for `openline-protocol`, `openline-proof-adapter`,
and `epistemic-swarm`. The three baseline directories are preserved
untouched (including bytecode caches); everything new lives here.

Run the checks:

    PYTHONDONTWRITEBYTECODE=1 python -m interop.checks [--report PATH]

Writes a JSON report, exits nonzero on failure. The baseline
reproduction executes the unmodified baseline sources against the
hard-coded `/home/workdir` paths; anything already present there is
moved aside first and restored afterwards, so the command can never
delete an existing store (covered by a sentinel-survival test).

## Schema

Unified receipt, `schema_version: 1`, `olp_version: "0.1"` (standardized
on the protocol's current version; the swarm's hard-coded `"1.0"` is
retired):

| field | meaning |
|---|---|
| `receipt_id` | uuid4 hex |
| `claim`, `action`, `result` | what was asserted / done / observed |
| `outcome` | explicit status: `success` \| `failure` \| `unknown` — never inferred from `result` text |
| `evidence_hash` | sha256 of canonical evidence ("" if none) |
| `tokens_used`, `timestamp`, `witness`, `next_use_note` | as in baseline |
| `parent_hash` | payload_hash of previous receipt (None at genesis) |
| `payload_hash` | sha256 over the canonical body |
| `signature` | Ed25519 over the payload_hash bytes (hex) |
| `signer_pubkey` | Ed25519 public key (hex) |
| `legacy` | present only on converted receipts (see below) |

## Signing

Ed25519 via the `cryptography` package. The signed envelope is
`{signature, payload_hash, signer_pubkey}`; the payload hash covers the
receipt body only (never itself or its own metadata).

Keys are configured **outside the repository**:

    OLP_LAB_SIGNING_KEY=...  # 64-hex-char seed (private)
    OLP_LAB_PUBLIC_KEY=...   # 64-hex-char public key

Never commit keys. Tests generate ephemeral keys. Verification works from
exported receipt JSON + the public key alone — no storage access needed.
Verification rejects: missing envelope fields, unsupported
`schema_version`, an embedded `signer_pubkey` that doesn't match the
verifying key, modified payloads, invalid signatures, and broken
predecessor links.

## Storage

Configurable root (`OLP_LAB_DIR` env, default `~/.olp-skills-lab`):

    <root>/receipts/<receipt_id>.json
    <root>/index.json   # {"format": "olp-skills-lab/index-1",
                        #  "receipts": [ids in emission order],
                        #  "head": <payload_hash of last | None>}
    <root>/index.lock   # dedicated lock file

- The index loader is the single canonical reader: missing file →
  empty; bare list (legacy swarm) → normalized to dict; dict with
  `receipts` (protocol or ours) → used as-is; explicit JSON `null` →
  rejected with `StorageError` *without modifying the file* (a null is
  not a missing file); anything else → fail closed with `StorageError`.
- Writes are atomic (temp file + `os.replace`, fsync) and serialized
  with an in-process lock plus `fcntl.flock` on the lock file, so
  concurrent emits from threads or processes cannot lose receipts.
- `emit_signed(build, signer)` performs head selection, signing, and
  the index append as **one transaction** under the exclusive lock, so
  concurrent writers can never sign against the same predecessor — the
  on-disk chain cannot fork. The full chain is verified after
  concurrent writes in the test suite.
- Restart recovery: a new `Storage(root)` (or `Orchestrator`) rebuilds
  in-memory state from disk; the chain continues via `head`.

APIs: `emit`, `load`, `list_ids`, `head`, `count`, `handoff_summary`.

## Conversions

`schema.CONVERTERS` maps each baseline format to the unified schema,
preserving original ids/timestamps/evidence hashes. Every converted
receipt carries a `legacy` block:

```json
{"source": "openline-protocol/0.1" | "epistemic-swarm/1.0" | "openline-proof-adapter",
 "signature_verified": false,
 "note": "<why: no signature in source / mock hash / caller-supplied parent>"}
```

Verification status is recorded honestly: none of the baseline formats
have cryptographic signatures, so converted receipts never verify as
signed. Conversion does not rewrite history — it re-houses it.

## Orchestration

`Orchestrator(storage, signer, public_key_hex, witnesses, domain,
fallback_executor)`:

- `run_task(task, executor)` — `executor` is any callable taking the
  task string and returning `{"result", "evidence", "tokens_used",
  "outcome"}`. `outcome` defaults to `"success"` when the executor
  returns normally and is `"failure"` on exception; it may also be set
  explicitly. The recorded `outcome` — never substring matching on
  `result` — drives drift measurement and `last_good` selection, so
  `"unsuccessful"` or `"not successful"` can never read as success.
- In-memory `orchestrator.receipts` is rebuilt from storage on init and
  appended after **every** emit (fixes the baseline's stale list).
- The reroute **decision** persists: it is derived from recorded
  `reroute` receipts, so restart → still routed to fallback (the
  fallback *callable* itself can't be persisted and must be
  re-supplied).
- Witnesses are real callables `(receipt, public_key) -> WitnessResult`.
  The built-in `chain_witness` verifies payload hash + Ed25519
  signature. Verdicts are emitted as `witness_verdicts` receipts; a
  rejection marks the task unaccepted. (The baseline OWA returned True
  unconditionally; it is retired.)
- COLE is invoked for real via the baseline `cole_monitor` (values
  recorded in `drift_check` receipts). Drift decisions use a
  **compatible** noise metric, `drift_epsilon` = recent task-failure
  fraction, against the baseline Terrynce per-domain thresholds via the
  real `tc_controller`: over threshold → `reroute` receipt + subsequent
  tasks use the fallback executor.
- Baseline modules are imported through `baseline_shim`, which
  neutralizes their import-time filesystem writes (`makedirs` on
  hard-coded paths) and import-time prints.

## Limitations

- Witnesses and executors are local callables, not sandboxed subagents.
- `drift_epsilon` deliberately replaces the baseline COLE variance
  metric for decisions (the baseline metric cannot reach its own
  thresholds — documented in REPORT.md); raw COLE values are still
  recorded for observability.
- Converted legacy receipts are carried, never signed; `verify_chain`
  rejects them explicitly rather than pretending.
- File locking is advisory (`fcntl`); all writers must go through
  `Storage`.
- Ed25519 security rests on the `cryptography` package and on keys kept
  outside the repo.
