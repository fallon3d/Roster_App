# FILE: rotation_core/hungarian.py
def hungarian(cost_matrix):
    """
    A simple (brute-force) implementation of the Hungarian assignment algorithm.
    Returns a list of column indices for each row.
    """
    from itertools import permutations

    n = len(cost_matrix)
    if n == 0:
        return []
    min_cost = float('inf')
    best_assign = None
    for perm in permutations(range(n)):
        cost = sum(cost_matrix[i][perm[i]] for i in range(n))
        if cost < min_cost:
            min_cost = cost
            best_assign = perm
    return list(best_assign) if best_assign else []
