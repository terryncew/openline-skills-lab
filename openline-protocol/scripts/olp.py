#!/usr/bin/env python3
"""
Minimal OpenLine Protocol (OLP) implementation for AI agent.
Portable receipts for handoffs, audits, state proofs.
"""

import json
import hashlib
import uuid
import datetime
import os
from typing import Dict, Any, Optional

OLP_DIR = "/home/workdir/.olp"
RECEIPTS_DIR = os.path.join(OLP_DIR, "receipts")
INDEX_FILE = os.path.join(OLP_DIR, "index.json")

def ensure_storage():
    """Initialize OLP storage directories and index."""
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'w') as f:
            json.dump({"receipts": [], "chain": []}, f, indent=2)

def compute_evidence_hash(data: Any) -> str:
    """Compute SHA256 hash of input evidence."""
    if isinstance(data, (dict, list)):
        data_str = json.dumps(data, sort_keys=True)
    else:
        data_str = str(data)
    return hashlib.sha256(data_str.encode('utf-8')).hexdigest()

def emit_olp_receipt(
    claim: str,
    action: str,
    result: str,
    evidence: Optional[Any] = None,
    tokens_used: int = 0,
    witness: str = "grok-agent",
    next_use_note: str = ""
) -> Dict[str, Any]:
    """Emit and store a minimal OLP receipt."""
    ensure_storage()
    
    receipt_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    evidence_hash = compute_evidence_hash(evidence) if evidence else ""
    
    receipt = {
        "olp_version": "0.1",
        "receipt_id": receipt_id,
        "claim": claim,
        "action": action,
        "evidence_hash": evidence_hash,
        "result": result,
        "tokens_used": tokens_used,
        "timestamp": timestamp,
        "witness": witness,
        "next_use_note": next_use_note
    }
    
    # Save receipt
    receipt_path = os.path.join(RECEIPTS_DIR, f"{receipt_id}.json")
    with open(receipt_path, 'w') as f:
        json.dump(receipt, f, indent=2)
    
    # Update index
    with open(INDEX_FILE, 'r') as f:
        index = json.load(f)
    index["receipts"].append(receipt_id)
    index["chain"].append(receipt)  # Keep lightweight chain
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)
    
    print(f"[OLP] Receipt emitted: {receipt_id} | {action} | {claim}")
    return receipt

def get_receipts(limit: int = 50) -> list:
    """Retrieve recent receipts."""
    ensure_storage()
    with open(INDEX_FILE, 'r') as f:
        index = json.load(f)
    return index["chain"][-limit:]

def show_olp_dashboard():
    """Simple CLI + HTML dashboard for receipts."""
    receipts = get_receipts(20)
    print("\n=== OLP Dashboard ===")
    print(f"Total receipts: {len(receipts)}")
    for r in reversed(receipts):
        print(f"[{r['timestamp'][:19]}] {r['action']} | {r['claim']} | {r['result']}")
    
    # Generate simple HTML
    html_path = os.path.join(OLP_DIR, "dashboard.html")
    html = f"""<!DOCTYPE html>
<html>
<head><title>OLP Dashboard</title><style>body{{font-family: monospace;}}</style></head>
<body>
<h1>OpenLine Protocol Dashboard</h1>
<p>Total Receipts: {len(receipts)}</p>
<table border="1">
<tr><th>Time</th><th>Action</th><th>Claim</th><th>Result</th><th>ID</th></tr>
"""
    for r in reversed(receipts):
        html += f"<tr><td>{r['timestamp'][:19]}</td><td>{r['action']}</td><td>{r['claim']}</td><td>{r['result']}</td><td>{r['receipt_id'][:8]}</td></tr>\n"
    html += "</table></body></html>"
    
    with open(html_path, 'w') as f:
        f.write(html)
    print(f"Dashboard saved to {html_path}")
    return html_path

def get_handoff_summary() -> str:
    """Generate portable handoff summary from receipts."""
    receipts = get_receipts(30)
    summary = "OLP Handoff Proof:\n"
    for r in receipts[-10:]:
        summary += f"- {r['timestamp'][:19]} {r['action']}: {r['claim']} -> {r['result']}\n"
    summary += f"\nFull chain hash: {compute_evidence_hash([r['receipt_id'] for r in receipts])}"
    return summary

if __name__ == "__main__":
    # Test
    emit_olp_receipt("Test emission", "test", "success", {"test": "data"})
    show_olp_dashboard()
