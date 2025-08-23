# FILE: rotation_core/hungarian.py
"""
Readable O(n^3) Hungarian / Kuh-Munkres implementation for square cost matrices.

- Minimizes total cost.
- Pads rectangular matrices to square with a large constant.
- Returns a list 'assign' where assign[row] = col index chosen for that row.
"""
from __future__ import annotations
import math
from typing import List, Tuple
import numpy as np


def _pad_to_square(cost: np.ndarray, pad_value: float) -> Tuple[np.ndarray, int, int]:
    r, c = cost.shape
    n = max(r, c)
    if r == c:
        return cost.copy(), r, c
    out = np.full((n, n), pad_value, dtype=float)
    out[:r, :c] = cost
    return out, r, c


def hungarian(cost_matrix: List[List[float]] | np.ndarray) -> List[int]:
    cost = np.array(cost_matrix, dtype=float)
    if cost.size == 0:
        return []

    BIG = 1e9
    sq, r, c = _pad_to_square(cost, BIG)

    # Step 1: Row/Col reductions
    sq -= sq.min(axis=1, keepdims=True)
    sq -= sq.min(axis=0, keepdims=True)

    n = sq.shape[0]
    # Masks
    starred = np.zeros_like(sq, dtype=bool)
    primed = np.zeros_like(sq, dtype=bool)
    covered_rows = np.zeros(n, dtype=bool)
    covered_cols = np.zeros(n, dtype=bool)

    # Step 2: Star zeros greedily (one per row/col)
    for i in range(n):
        for j in range(n):
            if sq[i, j] == 0 and not covered_rows[i] and not covered_cols[j]:
                starred[i, j] = True
                covered_rows[i] = True
                covered_cols[j] = True
    covered_rows[:] = False
    covered_cols[:] = False

    def cover_columns_of_starred():
        covered_cols[:] = starred.any(axis=0)

    cover_columns_of_starred()

    def find_a_zero():
        for i in range(n):
            if covered_rows[i]:
                continue
            for j in range(n):
                if covered_cols[j]:
                    continue
                if sq[i, j] == 0 and not primed[i, j] and not starred[i, j]:
                    return i, j
        return None

    def find_star_in_row(i):
        js = np.where(starred[i])[0]
        return int(js[0]) if js.size else None

    def find_star_in_col(j):
        is_ = np.where(starred[:, j])[0]
        return int(is_[0]) if is_.size else None

    def find_prime_in_row(i):
        js = np.where(primed[i])[0]
        return int(js[0]) if js.size else None

    while True:
        if covered_cols.sum() == n:
            break
        z = find_a_zero()
        while z is None:
            # Step 6: adjust matrix
            uncovered = ~covered_rows[:, None] & ~covered_cols[None, :]
            m = sq[uncovered].min()
            sq[~covered_rows, :] -= m
            sq[:, covered_cols] += m
            z = find_a_zero()
        i, j = z
        primed[i, j] = True
        star_j = find_star_in_row(i)
        if star_j is None:
            # Step 5: augmenting path
            path = [(i, j)]
            col = j
            row = find_star_in_col(col)
            while row is not None:
                path.append((row, col))
                col = find_prime_in_row(row)
                path.append((row, col))
                row = find_star_in_col(col)
            # flip stars/primes on path
            for (ri, cj) in path:
                if primed[ri, cj]:
                    starred[ri, cj] = True
                if starred[ri, cj] and (ri, cj) not in path:
                    starred[ri, cj] = False
            primed[:] = False
            covered_rows[:] = False
            covered_cols[:] = False
            cover_columns_of_starred()
        else:
            covered_rows[i] = True
            covered_cols[star_j] = False

    # Build assignment from stars; truncate to original r x c
    assign = [-1] * r
    for i in range(min(r, n)):
        js = np.where(starred[i])[0]
        if js.size:
            j = int(js[0])
            if j < c:
                assign[i] = j
    return assign
