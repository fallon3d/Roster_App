# FILE: tests/test_hungarian.py
from rotation_core.hungarian import hungarian

def test_hungarian_simple():
    matrix = [[4, 1, 3], [2, 0, 5], [3, 2, 2]]
    assignment = hungarian(matrix)
    # Check full matching
    assert set(assignment) == set(range(len(matrix)))
    cost = sum(matrix[i][assignment[i]] for i in range(len(matrix)))
    assert cost == 5
