import math

import numpy as np
from scipy.special import ndtr

from btree import localvol
from btree.batch import bs_european

R = 0.065


def _flat(v, Ts=(10 / 365, 40 / 365)):
    return localvol.Surface([{"T": T, "a": v * v * T, "b": 0.0, "rho": 0.0, "m": 0.0,
                              "sigma": 0.1} for T in Ts])


def test_flat_surface_has_flat_local_vol_and_prices_like_black():
    s = _flat(0.2)
    assert np.allclose(s.local_var(np.array([-0.1, 0.0, 0.1]), 25 / 365), 0.04)
    T, F = 30 / 365, 100.0
    got = localvol.tree_price(F, T, R, 600, lambda S: np.maximum(S - 100, 0),
                              lambda x, t: s.local_var(x, t))
    assert abs(got - bs_european([F], [100.0], [T], R, R, [0.2])[0]) < 0.003


def test_skewed_surface_is_repriced_and_its_digital_matches_the_smile():
    rows = [{"T": T, "a": 0.01 * T / 0.1, "b": 0.06 * T / 0.1, "rho": -0.6, "m": 0.0,
             "sigma": 0.1} for T in (10 / 365, 40 / 365)]
    s = localvol.Surface(rows)
    T, F = 30 / 365, 100.0
    cap = (3 * float(s.implied_vol(0.0, T))) ** 2

    def lv(x, t):
        return s.local_var(x, t, cap=cap)

    for k in (-0.05, 0.0, 0.03):
        K = F * math.exp(k)
        kind = "put" if k < 0 else "call"
        sign = -1 if kind == "put" else 1
        mkt = bs_european([F], [K], [T], R, R, [float(s.implied_vol(k, T))], kind)[0]
        got = localvol.tree_price(F, T, R, 1200, lambda S, K=K, g=sign: np.maximum(g * (S - K), 0),
                                  lv)
        assert abs(got - mkt) < 0.02
    k = math.log(1.02)
    w, w1, _, _ = s.w(k, T)
    sw = math.sqrt(w)
    d2 = -k / sw - sw / 2
    exact = 100 * math.exp(-R * T) * (ndtr(d2) - math.exp(-d2 * d2 / 2) / math.sqrt(2 * math.pi)
                                      * w1 / (2 * sw))
    got = localvol.tree_price(F, T, R, 1200, localvol.smoothed_digital(102.0), lv)
    assert abs(got - exact) < 0.1
