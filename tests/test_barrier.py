import math

import numpy as np

from btree import barrier
from btree.tree import bs_price

A = (100.0, 100.0, 95.0, 0.25, 0.065, 0.013, 0.2)


def test_far_barrier_is_a_plain_call_and_touching_it_is_worthless():
    S, K, _, T, r, q, v = A
    assert math.isclose(barrier.dao_closed(S, K, 1e-6, T, r, q, v), bs_price(S, K, T, r, q, v),
                        rel_tol=1e-9)
    assert barrier.dao_closed(95.0, K, 95.0, T, r, q, v) == 0.0


def test_aligned_trinomial_converges_to_the_formula_and_crr_does_not_settle():
    exact = barrier.dao_closed(*A)
    assert abs(barrier.dao_trinomial(*A, 800) - exact) < 0.005
    crr = [barrier.dao_crr(*A, n) - exact for n in range(400, 441, 4)]
    assert max(crr) - min(crr) > 0.05  # saw-tooth, not convergence
    S, _, H, T, r, q, v = A
    assert abs(barrier.dao_trinomial(S, 90.0, H, T, r, q, v, 800)
               - barrier.dao_closed(S, 90.0, H, T, r, q, v)) < 0.01  # barrier above the strike


def test_daily_checks_are_matched_by_the_shifted_barrier():
    S, K, H, _, r, q, v = A
    T = 30 / 365
    daily = barrier.dao_trinomial(S, K, H, T, r, q, 0.3, 21 * 20, monitor=20)
    cont = barrier.dao_closed(S, K, H, T, r, q, 0.3)
    shifted = barrier.dao_closed(S, K, barrier.bgk_barrier(H, 0.3, T / 21), T, r, q, 0.3)
    assert daily > cont  # fewer chances to knock out
    assert abs(shifted - daily) < abs(cont - daily) / 3
    assert np.isfinite(daily)
