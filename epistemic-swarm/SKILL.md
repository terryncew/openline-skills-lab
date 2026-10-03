---
name: epistemic-swarm
description: Build and operate the Epistemic Swarm — decentralized asynchronous research system using OpenLine Protocol for state, COLE for sanity, Terrynce Curve for failure thresholds, and OWA for arbitration. Trigger on requests to implement anti-fragile agent swarms, portable proofs, coherence monitoring, or graceful degradation in multi-agent setups.
---

# Epistemic Swarm Implementation

This skill implements the full Epistemic Swarm architecture as described. It extends the OLP layer for portable proofs and adds the other components.

## Core Principles
- **Mechanism-first**: All state via OLP receipts, no narrative bloat.
- **Assume drift**: Continuous monitoring + graceful failure.
- **Anti-fragile**: Orthogonal verification before merge.

## Components

### 1. OpenLine Protocol (OLP) Core
Already bootstrapped. Use `emit_olp_receipt()` for every action. 5-number digest = compact summary (e.g., claim_hash, state_id, κ, ε, timestamp).

### 2. Coherence Layer Engine (COLE)
Passive observer calculating:
- **Stress (κ)**: Entropy or inconsistency metric across recent receipts.
- **Rolling Signal Noise (ε)**: Variance in result quality / confidence over time window.

Implement as Python module that analyzes receipt chains.

### 3. Terrynce Curve & TC_controller
Mathematical thresholds per domain. Selector that triggers reroute on ε > threshold using last good receipt.

### 4. Orthogonal Witness Arbitration (OWA)
Spawn orthogonal sub-agents (logic, security, syntax) to verify OLP trail independently.

## Scripts
- `scripts/swarm.py`: Main orchestrator.
- `scripts/cole.py`: Coherence engine.
- `scripts/terrynce.py`: Curve + controller.
- `scripts/owa.py`: Arbitration.

## Usage
```python
from scripts.swarm import SwarmOrchestrator
orchestrator = SwarmOrchestrator()
orchestrator.run_task("Research X", witnesses=["logic", "security"])
```

Build the swarm by running the init and validation scripts below.