# FILE: rotation_core/fairness.py
from __future__ import annotations
from typing import Dict, List


def compute_quotas(num_players: int, total_slots: int) -> List[int]:
    """Minimum guarantee + even distribution remainder."""
    if num_players <= 0:
        return []
    base = total_slots // num_players
    remainder = total_slots % num_players
    quotas = [base] * num_players
    for i in range(remainder):
        quotas[i] += 1
    return quotas


def check_evenness(counts: List[int]) -> bool:
    return not counts or (max(counts) - min(counts) <= 1)


def at_cap_mask(appearances: Dict[str, int]) -> Dict[str, bool]:
    """Players at current +1 evenness cap."""
    if not appearances:
        return {}
    vals = list(appearances.values())
    mn = min(vals)
    cap = mn + 1
    return {pid: (cnt >= cap) for pid, cnt in appearances.items()}


def fairness_bias(appearances: Dict[str, int], alpha: float = 0.25) -> Dict[str, float]:
    """
    Bias factor favoring underused players: 1 + alpha*(max - count).
    """
    if not appearances:
        return {}
    mx = max(appearances.values())
    return {pid: (1.0 + alpha * (mx - cnt)) for pid, cnt in appearances.items()}
