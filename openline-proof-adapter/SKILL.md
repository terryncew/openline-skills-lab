---
name: openline-proof-adapter
description: Use this skill to add a minimal OpenLine Proof Adapter to the agent. Triggers on mentions of OpenLine, OLP, proof adapter, signed receipts, audit trail for agent actions, or the exact prompt to implement chained JSON receipts for tool calls, handoffs etc. Implements emission of signed receipts on events, chaining via parent_hash, and flagging issues.
---

# OpenLine Proof Adapter

## Overview

Implements a minimal OpenLine Protocol (OLP) adapter for auditability. Generates tamper-evident signed JSON receipts for key agent events. Chains them for provenance. Replaces full history with receipt chains for handoffs. Detects and flags anomalies.

## Core Receipt Structure

Every receipt is a JSON object:

```json
{
  "claim": "string summary of intent or assertion",
  "action": "tool_call | handoff | memory_write | retry | state_change | approval | cost_spike | ...",
  "evidence_hash": "SHA256 hash of input/context/evidence",
  "result": "success | failure | partial | {details}",
  "tokens_used": number,
  "timestamp": "ISO8601",
  "witness": "agent_id or signer",
  "parent_hash": "hash of previous receipt or null",
  "next_use_note": "guidance for downstream use",
  "signature": "Ed25519 or HMAC signature (mock for minimal)"
}
```

## Implementation Instructions

1. **Maintain State**:
   - Keep a list or chain of receipts in memory (or file `/home/workdir/.openline/receipts.jsonl`).
   - Track last_receipt_hash.
   - Global counters: total_tokens, loop_counter per action type.

2. **On Every Triggered Event** (before/after tool use, handoff, etc.):
   - Compute evidence_hash = SHA256 of (prompt + context snippet).
   - Generate receipt as above.
   - "Sign" it (mock with simple hash or use Python for real if possible).
   - Append to chain, update parent_hash.
   - Emit (log/print) the receipt JSON.
   - For handoffs: output only the receipt chain summary or latest receipt instead of full history.

3. **Flagging**:
   - **Loops**: If same action >3 times in chain, flag "LOOP_DETECTED".
   - **Lossy handoffs**: If receipt chain length < expected context, flag.
   - **Budget overruns**: If tokens_used > threshold, flag "BUDGET_OVERRUN".
   - **Unsafe actions**: Scan action for risky terms, flag "UNSAFE".

4. **Helper Functions** (use bash/Python scripts):
   - Use `scripts/generate_receipt.py` for creating receipts.
   - Load chain on startup.

5. **Integration**:
   - Hook into tool calling logic mentally: after every tool call response, generate receipt.
   - For responses involving handoffs: include receipt chain reference.
   - Persist chain across interactions where possible.

Always emit receipts transparently. Keep overhead minimal. Verify chain integrity by checking parent_hashes.

## Scripts Usage

- Run Python helpers for hashing/signing.
