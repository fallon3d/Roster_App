# FILE: rotation_core/fairness.py
def compute_quotas(num_players, total_slots):
    """
    Compute target appearances for each player using minimum guarantee.
    """
    base = total_slots // num_players
    remainder = total_slots % num_players
    quotas = [base] * num_players
    for i in range(remainder):
        quotas[i] += 1
    return quotas

def check_evenness(appearances):
    """
    Ensure the difference between max and min appearances is at most 1.
    """
    if not appearances:
        return True
    return max(appearances) - min(appearances) <= 1

def apply_fairness_bias(suitabilities, appearances):
    """
    Bias the suitability matrix to favor underused players.
    (Stub implementation; actual biasing logic goes here.)
    """
    return suitabilities
