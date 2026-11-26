"""Which delta hedges NIFTY options best from one day to the next?

Each trading day t, on the monthly expiry 20-60 days out (its own SVI slice, forward F_t), options
are struck at fixed rupee strikes K = F_t e^k for k in KS (puts below the forward, calls at or
above). The "market" price is Black-76 at the slice's SVI volatility at the strike; tomorrow the
same strike and expiry are re-priced from tomorrow's slice. The hedge holds delta units of the
expiry's forward (futures), so the hedging error is dC - delta dF. Deltas:
- Black: Black-76 delta at the strike's own volatility (vols stay with the strike);
- smile tree: re-price the local-volatility tree of `btree.localvol` with the forward moved +-0.5%,
  local volatility held fixed as a function of the price level;
- same shape (implied-vol-surface finding 4's rule): tomorrow's vol at log-moneyness k is today's
  at k plus b x S x (dF / F), S the at-the-money slope d(vol)/dk. A fixed strike's k moves by
  -dF/F, so its vol changes by (b S - sigma'(k)) dF/F, and the delta is Black's plus
  vega x (b S - sigma'(k)) / F, sigma'(k) the smile's slope at the strike. b = 1 is that repo's
  choice on 2015-2020; `same_shape_delta` gives any b from the stored pieces.
"""

import math

import numpy as np
import pandas as pd
from scipy.special import ndtr

from btree import localvol

KS = (-0.05, 0.0, 0.03)
B_SAME_SHAPE = 1.0  # implied-vol-surface finding 4: chosen on 2015-2020
H = 0.005


def black(F, K, T, r, v, kind):
    vt = v * math.sqrt(T)
    d1 = math.log(F / K) / vt + vt / 2
    d2 = d1 - vt
    df = math.exp(-r * T)
    if kind == "call":
        return df * (F * ndtr(d1) - K * ndtr(d2)), df * ndtr(d1), df * F * math.sqrt(T) * math.exp(
            -d1 * d1 / 2) / math.sqrt(2 * math.pi)
    return (df * (K * ndtr(-d2) - F * ndtr(-d1)), -df * ndtr(-d1),
            df * F * math.sqrt(T) * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi))


def _vol(p, F, K, T):
    k = math.log(K / F)
    a, b, rho, m, s = (p[x] for x in localvol.PARAMS)
    w = a + b * (rho * (k - m) + math.sqrt((k - m) ** 2 + s * s))
    return math.sqrt(max(w, 1e-12) / T)


def _dvol_dk(p, k, T):
    """Slope of the SVI smile, d(vol)/dk, at log-moneyness k."""
    a, b, rho, m, s = (p[x] for x in localvol.PARAMS)
    root = math.sqrt((k - m) ** 2 + s * s)
    w = a + b * (rho * (k - m) + root)
    return b * (rho + (k - m) / root) / (2 * math.sqrt(max(w, 1e-12) * T))


def same_shape_delta(d, b):
    """Same-shape delta for multiplier b from a `day_cases` table."""
    return d["d_bs"] + d["vega"] * (b * d["S"] - d["sk"]) / d["F0"]


def _slope(p, T):
    a, b, rho, m, s = (p[x] for x in localvol.PARAMS)
    w0 = a + b * (rho * (-m) + math.sqrt(m * m + s * s))
    return b * (rho - m / math.sqrt(m * m + s * s)) / (2 * math.sqrt(w0 * T))


def day_cases(svi: pd.DataFrame, r: float, steps_per_day: int = 42, every: int = 1) -> pd.DataFrame:
    """Hedging errors for each day pair (every `every`-th day) and strike, for the three deltas."""
    svi = svi[svi["converged"]]
    by = {d: g for d, g in svi.groupby("date")}
    dates = sorted(by)
    rows = []
    for t0, t1 in list(zip(dates[:-1], dates[1:], strict=True))[::every]:
        g0 = by[t0]
        mon = g0[g0["monthly"] & g0["days"].between(20, 60)].sort_values("days")
        if mon.empty:
            continue
        s0 = mon.iloc[0]
        s1 = by[t1][by[t1]["expiry"] == s0["expiry"]]
        if s1.empty:
            continue
        s1 = s1.iloc[0]
        p0 = {x: s0[x] for x in localvol.PARAMS}
        p1 = {x: s1[x] for x in localvol.PARAMS}
        F0, F1, T0, T1 = s0["F"], s1["F"], s0["T"], s1["T"]
        srf = localvol.Surface(g0[g0["days"] >= 7].to_dict("records"))
        atm = float(srf.implied_vol(0.0, T0))
        cap = (3 * atm) ** 2
        S = _slope(p0, T0)
        n = max(200, int(steps_per_day * s0["days"]))
        for k in KS:
            K = F0 * math.exp(k)
            kind = "put" if k < 0 else "call"
            c0, d_bs, vega = black(F0, K, T0, r, _vol(p0, F0, K, T0), kind)
            c1 = black(F1, K, T1, r, _vol(p1, F1, K, T1), kind)[0]
            sign = -1.0 if kind == "put" else 1.0

            def pay(Sx, K=K, sign=sign):
                return np.maximum(sign * (Sx - K), 0)

            up, dn = (localvol.tree_price(
                F0 * (1 + h), T0, r, n, pay,
                lambda x, t, h=h, srf=srf, cap=cap: srf.local_var(x + math.log(1 + h), t,
                                                                 cap=cap))
                for h in (H, -H))
            d_lv = (up - dn) / (2 * H * F0)
            sk = _dvol_dk(p0, k, T0)
            d_ss = d_bs + vega * (B_SAME_SHAPE * S - sk) / F0
            dC, dF = c1 - c0, F1 - F0
            rows.append({"date": t1, "k": k, "dC": dC, "dF": dF, "F0": F0, "unhedged": dC,
                         "black": dC - d_bs * dF, "smile_tree": dC - d_lv * dF,
                         "same_shape": dC - d_ss * dF, "d_bs": d_bs, "d_lv": d_lv, "d_ss": d_ss,
                         "vega": vega, "S": S, "sk": sk})
    return pd.DataFrame(rows)
