import numpy as np

from btree import batch

A = ([100.0], [95.0], [0.25], 0.05, 0.02, [0.25])


def test_formula_greeks_match_finite_differences_of_the_formula():
    for kind in ("call", "put"):
        d, g, t = (x[0] for x in batch.bs_greeks(*A, kind=kind))
        h = 1e-3
        up = batch.bs_european([100 + h], *A[1:], kind)[0]
        dn = batch.bs_european([100 - h], *A[1:], kind)[0]
        mid = batch.bs_european(*A, kind)[0]
        later = batch.bs_european([100.0], [95.0], [0.25 - 1e-5], 0.05, 0.02, [0.25], kind)[0]
        assert np.isclose(d, (up - dn) / (2 * h), atol=1e-6)
        assert np.isclose(g, (up - 2 * mid + dn) / h**2, rtol=1e-4)
        assert np.isclose(t, (later - mid) / 1e-5, rtol=1e-3)


def test_leisen_reimer_node_theta_is_wrong_until_moved_to_todays_price():
    _, _, bt = batch.bs_greeks(*A, kind="put")
    _, _, raw = batch.node_greeks(*A, 101, kind="put", method="lr")
    _, _, fixed = batch.node_greeks(*A, 101, kind="put", method="lr", correct=True)
    assert abs(raw[0] / bt[0] - 1) > 0.2
    assert abs(fixed[0] / bt[0] - 1) < 0.01


def test_crr_node_greeks_converge():
    bd, bg, _ = batch.bs_greeks(*A, kind="call")
    d, g, _ = batch.node_greeks(*A, 800, kind="call", method="crr")
    assert abs(d[0] - bd[0]) < 2e-4 and abs(g[0] / bg[0] - 1) < 2e-3
