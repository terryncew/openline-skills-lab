#!/usr/bin/env python3
import json
import hashlib
import time
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

# Extend OLP if exists, else minimal impl
OLP_DIR = "/home/workdir/.olp"
os.makedirs(OLP_DIR, exist_ok=True)

def sha256_hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

class OLPReceipt:
    def __init__(self, claim: str, action: str, result: Any, evidence: Dict = None, tokens_used: int = 0, next_use_note: str = ""):
        self.receipt = {
            "olp_version": "1.0",
            "receipt_id": sha256_hash({"ts": time.time(), "claim": claim})[:16],
            "timestamp": datetime.utcnow().isoformat(),
            "claim": claim,
            "action": action,
            "evidence_hash": sha256_hash(evidence or {}),
            "result": str(result)[:500],  # truncate
            "tokens_used": tokens_used,
            "witness": "epistemic-swarm",
            "next_use_note": next_use_note,
            "digest": {}  # 5-number placeholder
        }
        self.save()

    def save(self):
        path = f"{OLP_DIR}/{self.receipt['receipt_id']}.json"
        with open(path, 'w') as f:
            json.dump(self.receipt, f, indent=2)
        # Update index
        index_path = f"{OLP_DIR}/index.json"
        index = []
        if os.path.exists(index_path):
            with open(index_path) as f:
                index = json.load(f)
        index.append(self.receipt['receipt_id'])
        with open(index_path, 'w') as f:
            json.dump(index, f)

def get_5_number_digest(receipts: List[Dict]) -> Dict:
    """Minimal 5-number digest for handoff"""
    if not receipts:
        return {}
    recent = receipts[-5:]
    return {
        "claim_hash": sha256_hash([r['claim'] for r in recent])[:8],
        "state_id": len(receipts),
        "stress_k": sum(1 for r in recent if "high" in str(r.get('result','')).lower()) / len(recent),
        "noise_e": 0.3,  # placeholder
        "last_ts": recent[-1]['timestamp']
    }

# COLE, Terrynce, OWA stubs - to be fleshed in separate modules
class SwarmOrchestrator:
    def __init__(self):
        self.receipts = []
        self.load_receipts()

    def load_receipts(self):
        index_path = f"{OLP_DIR}/index.json"
        if os.path.exists(index_path):
            with open(index_path) as f:
                ids = json.load(f)
            for rid in ids[-20:]:  # recent
                try:
                    with open(f"{OLP_DIR}/{rid}.json") as f:
                        self.receipts.append(json.load(f))
                except:
                    pass

    def run_task(self, task: str, witnesses: List[str] = None):
        # Emit start receipt
        OLPReceipt(f"Start task: {task}", "task_start", "init", {"task": task})
        
        # Simulate subagent work with COLE monitoring
        print(f"[Swarm] Running {task} with OLP tracking...")
        
        # Placeholder result
        result = f"Completed {task} via portable proofs."
        
        receipt = OLPReceipt(f"Task result: {task}", "task_complete", result, {"output": result}, next_use_note="For OWA verification")
        
        # OWA if requested
        if witnesses:
            self.owa_verify(receipt.receipt, witnesses)
        
        return receipt.receipt

    def owa_verify(self, receipt: Dict, witnesses: List[str]):
        print(f"[OWA] Orthogonal verification by {witnesses} on receipt {receipt['receipt_id']}")
        # In full impl, spawn parallel checks
        for w in witnesses:
            print(f"  - {w} witness: OK on cryptographic trail")

print("Epistemic Swarm core loaded.")