import math

import numpy as np
import pandas as pd

from btree import hedge


def test_black_delta_and_vega_match_finite_differences():
    F, K, T, r, v = 100.0, 95.0, 0.1, 0.065, 0.2
    for kind in ("call", "put"):
        p, d, vega = hedge.black(F, K, T, r, v, kind)
        h = 1e-4
        assert math.isclose(d, (hedge.black(F + h, K, T, r, v, kind)[0]
                                - hedge.black(F - h, K, T, r, v, kind)[0]) / (2 * h), rel_tol=1e-6)
        assert math.isclose(vega, (hedge.black(F, K, T, r, v + h, kind)[0]
                                   - hedge.black(F, K, T, r, v - h, kind)[0]) / (2 * h),
                            rel_tol=1e-6)


def test_on_a_flat_smile_all_three_deltas_agree():
    rows = []
    e = pd.Timestamp("2024-02-29")
    for d, F in ((pd.Timestamp("2024-01-29"), 100.0), (pd.Timestamp("2024-01-30"), 101.0)):
        for exp, monthly in ((e, True), (pd.Timestamp("2024-03-28"), True)):
            T = (exp - d).days / 365
            rows.append({"date": d, "expiry": exp, "days": (exp - d).days, "T": T, "F": F,
                         "monthly": monthly, "converged": True, "a": 0.04 * T, "b": 0.0,
                         "rho": 0.0, "m": 0.0, "sigma": 0.1})
    out = hedge.day_cases(pd.DataFrame(rows), 0.065, steps_per_day=30)
    assert len(out) == len(hedge.KS)
    assert np.allclose(out["d_ss"], out["d_bs"])
    assert np.allclose(out["d_lv"], out["d_bs"], atol=2e-3)


def test_same_shape_delta_matches_a_finite_difference_of_the_rule_on_a_skewed_smile():
    # rule: tomorrow's vol at log-moneyness k = today's at k + b S (dF/F), S the ATM slope
    p = {"a": 0.001, "b": 0.02, "rho": -0.7, "m": 0.01, "sigma": 0.05}
    F, T, r, b = 100.0, 0.08, 0.065, 1.0
    S = hedge._slope(p, T)
    for k in (-0.05, 0.0, 0.03):
        K = F * math.exp(k)
        kind = "put" if k < 0 else "call"
        _, d_bs, vega = hedge.black(F, K, T, r, hedge._vol(p, F, K, T), kind)
        row = pd.DataFrame({"d_bs": [d_bs], "vega": [vega], "S": [S],
                            "sk": [hedge._dvol_dk(p, k, T)], "F0": [F]})
        got = float(hedge.same_shape_delta(row, b).iloc[0])

        def price(Fx, K=K, kind=kind):
            vol = hedge._vol(p, Fx, K, T) + b * S * math.log(Fx / F)
            return hedge.black(Fx, K, T, r, vol, kind)[0]

        h = 1e-3
        fd = (price(F + h) - price(F - h)) / (2 * h)
        assert abs(got - fd) < 2e-4
