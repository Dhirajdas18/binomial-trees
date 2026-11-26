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
