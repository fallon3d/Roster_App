# FILE: tests/test_fairness.py
from rotation_core.fairness import compute_quotas, check_evenness

def test_compute_quotas():
    quotas = compute_quotas(4, 10)
    assert sum(quotas) == 10
    assert max(quotas) - min(quotas) <= 1

def test_evenness_true_and_false():
    assert check_evenness([2, 2, 3, 2])
    assert not check_evenness([1, 5, 1, 1])
