---
name: openline-protocol
description: Add minimal OpenLine Protocol (OLP) layer for portable AI handoffs and audit. Triggers on any mention of OLP, OpenLine, handoff proof, receipts, audit trail, or when user requests minimal proof logging for tool calls/memory/subagents. Use for implementing verifiable state changes.
---

# OpenLine Protocol

## Overview

Implements a minimal OLP for this agent: emits JSON receipts for tool calls, subagent interactions, memory writes, retries, state changes. Receipts enable portable proof on handoff (instead of full history). Stores locally, provides dashboard.

## Core Concepts

**Receipt JSON structure:**
```json
{
  "olp_version": "0.1",
  "claim": "short description of intent/proof",
  "action": "tool_call|memory_write|subagent|retry|state_change|...",
  "evidence_hash": "sha256 of input/evidence",
  "result": "success|failure|summary",
  "tokens_used": 1234,
  "timestamp": "ISO8601",
  "witness": "grok-agent-id",
  "next_use_note": "handoff hint or continuation",
  "receipt_id": "unique-uuid"
}
```

## Implementation Instructions

1. **Receipt Emitter**: Always call `emit_olp_receipt()` after significant actions (tools, memory, etc.). Use scripts/olp.py.

2. **Storage**: Receipts in `/home/workdir/.olp/receipts/` as individual JSON files + index.

3. **Dashboard**: Simple HTML/CLI viewer at `show_olp_dashboard()`.

4. **Handoff**: On handoff, summarize via receipts chain instead of raw history.

Use Python for core logic (reliable, hashable). Integrate via skill hooks in agent flows.

## Scripts Usage

- `scripts/olp.py`: Core library for emit, store, verify, dashboard.
- Initialize storage on first use.

## Triggers for Activation
- User requests OLP layer addition
- Handoff preparation
- Audit/trail needs

Keep receipts minimal (<1KB each) for portability.