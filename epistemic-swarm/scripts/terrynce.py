#!/usr/bin/env python3
from typing import Dict

def get_terrynce_threshold(domain: str = "general") -> float:
    """Terrynce Curve thresholds"""
    thresholds = {
        "general": 0.45,
        "coding": 0.35,
        "research": 0.5,
        "data": 0.4
    }
    return thresholds.get(domain, 0.45)

def tc_controller(noise_e: float, domain: str, last_good_receipt: Dict) -> Dict:
    """Graceful failure handler"""
    thresh = get_terrynce_threshold(domain)
    if noise_e > thresh:
        return {
            "action": "reroute",
            "reason": f"ε={noise_e:.2f} > threshold {thresh}",
            "last_good": last_good_receipt['receipt_id'] if last_good_receipt else None,
            "to": "fresh_node"
        }
    return {"action": "continue"}

print("Terrynce Curve controller initialized.")