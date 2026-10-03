#!/usr/bin/env python3
import json
import statistics
from typing import List, Dict

def calculate_stress_k(receipts: List[Dict]) -> float:
    """Stress (κ): inconsistency metric"""
    if len(receipts) < 3:
        return 0.0
    results = [len(str(r.get('result', ''))) for r in receipts[-10:]]
    return statistics.stdev(results) / (sum(results)/len(results) + 1) if results else 0.0

def calculate_noise_e(receipts: List[Dict]) -> float:
    """Rolling signal noise (ε)"""
    if len(receipts) < 5:
        return 0.2
    confidences = [0.8 if "success" in str(r.get('result','')).lower() else 0.4 for r in receipts[-20:]]
    return statistics.variance(confidences) if len(confidences) > 1 else 0.0

def cole_monitor(receipts: List[Dict]) -> Dict:
    """Passive COLE observer"""
    return {
        "stress_kappa": calculate_stress_k(receipts),
        "noise_epsilon": calculate_noise_e(receipts),
        "status": "coherent" if calculate_noise_e(receipts) < 0.5 else "drifting"
    }

print("COLE coherence layer ready.")