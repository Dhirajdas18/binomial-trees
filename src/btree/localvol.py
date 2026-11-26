"""A tree that fits the smile: local volatility from one day's SVI slices, on a trinomial grid.

Total implied variance w(k, T) (k = ln(K / F_T)) between two slices is interpolated linearly in T
at fixed k (before the first slice, w grows in proportion to T). Dupire's local variance in these
units (Gatheral):
    sigma_loc^2(k, T) = (dw/dT) / [1 - (k / w) w' + (1/4)(-1/4 - 1/w + k^2 / w^2) w'^2 + w'' / 2],
with w', w'' the k-derivatives (exact for SVI); the denominator is the butterfly function g(k).
The tree runs on x = ln(S_t / F_t) (forward units, so the drift is only -sigma^2 / 2): a fixed
spacing dx >= max local vol x sqrt(dt), up/middle/down probabilities from each node's local
variance. This is the stable modern form of Derman and Kani's implied tree.
"""

import math

import numpy as np

PARAMS = ("a", "b", "rho", "m", "sigma")


def _svi(p, k):
    a, b, rho, m, s = (p[x] for x in PARAMS)
    root = np.sqrt((k - m) ** 2 + s * s)
    w = a + b * (rho * (k - m) + root)
    w1 = b * (rho + (k - m) / root)
    w2 = b * s * s / root**3
    return w, w1, w2


class Surface:
    """One day's SVI slices (rows with T, a, b, rho, m, sigma), sorted by maturity."""

    def __init__(self, slices):
        self.s = sorted(({x: float(r[x]) for x in (*PARAMS, "T")} for r in slices),
                        key=lambda r: r["T"])

    def w(self, k, T):
        """Total variance and its k-derivatives and T-derivative at (k, T)."""
        s = self.s
        if T <= s[0]["T"]:
            w, w1, w2 = _svi(s[0], k)
            f = T / s[0]["T"]
            return w * f, w1 * f, w2 * f, w / s[0]["T"]
        i = next((i for i in range(1, len(s)) if T <= s[i]["T"]), len(s) - 1)
        a, b = s[i - 1], s[i]  # past the last slice: extend the last two linearly
        wa, a1, a2 = _svi(a, k)
        wb, b1, b2 = _svi(b, k)
        u = (T - a["T"]) / (b["T"] - a["T"])
        wt = (wb - wa) / (b["T"] - a["T"])
        return (1 - u) * wa + u * wb, (1 - u) * a1 + u * b1, (1 - u) * a2 + u * b2, wt

    def implied_vol(self, k, T):
        return np.sqrt(np.maximum(self.w(k, T)[0], 1e-12) / T)

    def local_var(self, k, T, floor=1e-4, cap=4.0):
        """Dupire local variance (a year), floored and capped for stability."""
        w, w1, w2, wt = self.w(k, T)
        w = np.maximum(w, 1e-12)
        g = 1 - k * w1 / w + 0.25 * (-0.25 - 1 / w + k * k / (w * w)) * w1 * w1 + 0.5 * w2
        lv = np.maximum(wt, 1e-8) / np.maximum(g, 1e-3)
        return np.clip(lv, floor, cap)


def tree_price(F_T, T, r, n, payoff, local_var, forward_ratio=None, alive=None,
               check_every=1, width=6.0):
    """Backward induction on the forward-units trinomial grid.

    payoff(S_T) at expiry; local_var(x, t) -> variance at x = ln(S_t / F_t), time t;
    forward_ratio(t) = F_t / F_T (1 if None); alive(S, t) -> bool array, applied every
    `check_every` steps (a barrier). Returns today's value."""
    dt = T / n
    half = width * math.sqrt(float(local_var(np.array([0.0]), T)[0]) * T)  # grid half-width in x
    probe = np.linspace(-half, half, 241)
    vmax = max(float(np.max(local_var(probe, t))) for t in np.linspace(dt, T, 16))
    dx = 1.05 * math.sqrt(vmax * dt)  # keeps every middle probability >= 0
    J = int(math.ceil(half / dx)) + 2
    x = np.arange(-J, J + 1) * dx
    fr = forward_ratio or (lambda t: 1.0)
    v = payoff(F_T * np.exp(x))
    disc = math.exp(-r * dt)
    for i in range(n - 1, -1, -1):
        t = i * dt
        var = np.minimum(local_var(x, max(t, 1e-6)), dx * dx / dt)  # stability: a <= 1
        mu = -0.5 * var
        a = var * dt / dx**2
        b = mu * dt / dx
        pu, pd = 0.5 * (a + b), 0.5 * (a - b)
        pm = 1 - pu - pd
        nv = np.empty_like(v)
        nv[1:-1] = disc * (pu[1:-1] * v[2:] + pm[1:-1] * v[1:-1] + pd[1:-1] * v[:-2])
        nv[0], nv[-1] = 2 * nv[1] - nv[2], 2 * nv[-2] - nv[-3]  # linear at the far edges
        v = nv
        if alive is not None and i % check_every == 0 and i > 0:
            v = np.where(alive(F_T * fr(t) * np.exp(x), t), v, 0.0)
    return float(np.interp(0.0, x, v))


def smoothed_digital(K, amount=100.0):
    """Cash-or-nothing call payoff averaged over each node's grid cell (cell edges at the
    log-price midpoints between nodes, the covered share measured in price), so a strike between
    two nodes doesn't make the price jump with the grid."""
    def pay(S):
        lo = np.sqrt(S * np.r_[S[0] ** 2 / S[1], S[:-1]])
        hi = np.sqrt(S * np.r_[S[1:], S[-1] ** 2 / S[-2]])
        return amount * np.clip((hi - K) / (hi - lo), 0, 1)
    return pay


def month_end_surfaces(min_days: int = 7, need_days: float = 30):
    """[(date, Surface, F at need_days)] for the last trading day of each month whose slices
    reach `need_days`, from implied-vol-surface's SVI table."""
    import pandas as pd

    from btree.data import iv_dir

    svi = pd.read_parquet(iv_dir() / "data" / "derived" / "svi_daily.parquet")
    svi = svi[svi["converged"] & (svi["days"] >= min_days)]
    dates = pd.DatetimeIndex(sorted(svi["date"].unique()))
    out = []
    for d in pd.Series(dates, index=dates).groupby([dates.year, dates.month]).max():
        g = svi[svi["date"] == d].sort_values("T")
        if g["days"].max() < need_days:
            continue
        F = float(np.exp(np.interp(need_days / 365, g["T"], np.log(g["F"]))))
        out.append((d, Surface(g.to_dict("records")), F))
    return out
