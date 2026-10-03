import json
import hashlib
import time
import os
from datetime import datetime

RECEIPTS_DIR = '/home/workdir/.openline'
os.makedirs(RECEIPTS_DIR, exist_ok=True)
RECEIPT_FILE = os.path.join(RECEIPTS_DIR, 'receipts.jsonl')

def compute_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def generate_receipt(claim, action, evidence, result, tokens_used, witness="grok-openline-adapter", parent_hash=None, next_use_note=""):
    evidence_hash = compute_hash(evidence)
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    receipt = {
        "claim": claim,
        "action": action,
        "evidence_hash": evidence_hash,
        "result": result,
        "tokens_used": tokens_used,
        "timestamp": timestamp,
        "witness": witness,
        "parent_hash": parent_hash,
        "next_use_note": next_use_note,
        "signature": compute_hash({"payload": locals()})  # mock signature
    }
    
    # Append to chain
    with open(RECEIPT_FILE, 'a') as f:
        f.write(json.dumps(receipt) + '\n')
    
    print("=== OPENLINE RECEIPT ===")
    print(json.dumps(receipt, indent=2))
    print("========================")
    
    return receipt

if __name__ == "__main__":
    # Example usage
    generate_receipt("Test claim", "tool_call", {"input": "example"}, "success", 42)
