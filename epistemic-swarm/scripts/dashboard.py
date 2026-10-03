#!/usr/bin/env python3
import json
import os
from datetime import datetime

OLP_DIR = "/home/workdir/.olp"

def show_dashboard():
    index_path = f"{OLP_DIR}/index.json"
    if not os.path.exists(index_path):
        print("No receipts yet.")
        return
    with open(index_path) as f:
        ids = json.load(f)
    print(f"Epistemic Swarm Dashboard — {len(ids)} receipts")
    print("="*60)
    for rid in ids[-10:]:
        try:
            with open(f"{OLP_DIR}/{rid}.json") as f:
                rec = json.load(f)
            print(f"[{rec['timestamp']}] {rec['claim'][:80]} -> {rec.get('result','')[:60]}")
        except:
            pass
    print("\nHandoff ready: Use get_5_number_digest() for portable state.")

if __name__ == "__main__":
    show_dashboard()