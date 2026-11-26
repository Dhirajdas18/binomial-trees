"""European tree prices for many options at once.

A European option on an n-step recombining tree needs no backward induction: its value is the
discounted binomial average of the payoffs at expiry,
    e^{-rT} * sum_j C(n, j) p^j (1 - p)^(n - j) payoff(S u^j d^(n - j)),
which is the same number `tree.crr` gets by stepping back (tested), but costs O(n) per option and
vectorises across options. Used for the convergence studies on real NIFTY quotes.
"""

import numpy as np
from scipy.special import ndtr
from scipy.stats import binom


def _european(S, K, T, r, u, d, p, n, kind):
    j = np.arange(n + 1)
    ST = S[:, None] * u[:, None] ** j * d[:, None] ** (n - j)
    pay = np.maximum(ST - K[:, None], 0) if kind == "call" else np.maximum(K[:, None] - ST, 0)
    w = binom.pmf(j[None, :], n, p[:, None])
    return np.exp(-r * T) * (w * pay).sum(axis=1)


def crr_european(S, K, T, r, q, sigma, n, kind="call"):
    """CRR European prices for arrays S, K, T, sigma (r, q scalars or arrays), n steps."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    return _european(S, K, T, r, u, d, p, n, kind)


def _pp2(z, n):
    """Peizer-Pratt inversion, method 2 (vectorised)."""
    return 0.5 + np.sign(z) * 0.5 * np.sqrt(
        1 - np.exp(-((z / (n + 1 / 3 + 0.1 / (n + 1))) ** 2) * (n + 1 / 6)))


def lr_european(S, K, T, r, q, sigma, n, kind="call"):
    """Leisen-Reimer European prices (odd n; an even n uses n + 1), vectorised."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    n = n if n % 2 else n + 1
    dt = T / n
    vt = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vt
    d2 = d1 - vt
    p, p1 = _pp2(d2, n), _pp2(d1, n)
    g = np.exp((r - q) * dt)
    u = g * p1 / p
    d = (g - p * u) / (1 - p)
    return _european(S, K, T, r, u, d, p, n, kind)


def bs_european(S, K, T, r, q, sigma, kind="call"):
    """Black-Scholes prices, vectorised."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    vt = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vt
    d2 = d1 - vt
    if kind == "call":
        return S * np.exp(-q * T) * ndtr(d1) - K * np.exp(-r * T) * ndtr(d2)
    return K * np.exp(-r * T) * ndtr(-d2) - S * np.exp(-q * T) * ndtr(-d1)


def _params(S, K, T, r, q, sigma, n, method):
    """(n, u, d, p) arrays for a CRR or Leisen-Reimer tree."""
    if method == "crr":
        dt = T / n
        u = np.exp(sigma * np.sqrt(dt))
        d = 1 / u
        p = (np.exp((r - q) * dt) - d) / (u - d)
        return n, u, d, p
    n = n if n % 2 else n + 1
    dt = T / n
    vt = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vt
    d2 = d1 - vt
    p, p1 = _pp2(d2, n), _pp2(d1, n)
    g = np.exp((r - q) * dt)
    u = g * p1 / p
    return n, u, (g - p * u) / (1 - p), p


def node_greeks(S, K, T, r, q, sigma, n, kind="call", method="crr", correct=False):
    """Delta, gamma and theta (a year) read off the tree's first two steps (European), the
    textbook way: delta from the two step-1 nodes, gamma from the three step-2 nodes, theta from
    the middle step-2 node against today (for Leisen-Reimer that node is not at today's price,
    since u d != 1). With `correct`, delta and theta are moved back to today's price with a
    second-order Taylor step: the step-1 difference measures delta at the midpoint S(u + d)/2, and
    the middle step-2 node sits at S u d, not S."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    n, u, d, p = _params(S, K, T, r, q, sigma, n, method)
    dt = T / n

    def v(Sn, steps, Tn):
        return _european(Sn, K, Tn, r, u, d, p, steps, kind)

    f0 = v(S, n, T)
    fu, fd = v(S * u, n - 1, T - dt), v(S * d, n - 1, T - dt)
    fuu, fud, fdd = (v(S * u * u, n - 2, T - 2 * dt), v(S * u * d, n - 2, T - 2 * dt),
                     v(S * d * d, n - 2, T - 2 * dt))
    delta = (fu - fd) / (S * u - S * d)
    gamma = ((fuu - fud) / (S * u * u - S * u * d) - (fud - fdd) / (S * u * d - S * d * d)) / (
        0.5 * (S * u * u - S * d * d))
    if correct:
        delta = delta - gamma * (S * (u + d) / 2 - S)
        move = S * u * d - S
        theta = (fud - f0 - delta * move - 0.5 * gamma * move**2) / (2 * dt)
    else:
        theta = (fud - f0) / (2 * dt)
    return delta, gamma, theta


def bump_greeks(S, K, T, r, q, sigma, n, kind="call", h=0.005, days=1):
    """Delta, gamma and theta (a year) by re-pricing a Leisen-Reimer tree with the price moved
    by +-h (relative) and with `days` less to expiry."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    up, mid, dn = (lr_european(S * (1 + s), K, T, r, q, sigma, n, kind) for s in (h, 0, -h))
    dS = S * h
    later = lr_european(S, K, T - days / 365, r, q, sigma, n, kind)
    return (up - dn) / (2 * dS), (up - 2 * mid + dn) / dS**2, (later - mid) / (days / 365)


def bs_greeks(S, K, T, r, q, sigma, kind="call"):
    """Black-Scholes delta, gamma and theta (a year; the value's change as time passes)."""
    from scipy.stats import norm

    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    vt = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vt
    d2 = d1 - vt
    n1 = norm.pdf(d1)
    gamma = np.exp(-q * T) * n1 / (S * vt)
    common = -S * np.exp(-q * T) * n1 * sigma / (2 * np.sqrt(T))
    if kind == "call":
        delta = np.exp(-q * T) * ndtr(d1)
        theta = common + q * S * np.exp(-q * T) * ndtr(d1) - r * K * np.exp(-r * T) * ndtr(d2)
    else:
        delta = -np.exp(-q * T) * ndtr(-d1)
        theta = common - q * S * np.exp(-q * T) * ndtr(-d1) + r * K * np.exp(-r * T) * ndtr(-d2)
    return delta, gamma, theta


def american(S, K, T, r, q, sigma, n, kind="put", method="lr"):
    """American prices for many options at once: backward induction with exercise at every node,
    vectorised across options (one row per option, one column per node)."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    n, u, d, p = _params(S, K, T, r, q, sigma, n, method)
    disc = np.exp(-r * T / n)[:, None]
    j = np.arange(n + 1)
    st = S[:, None] * u[:, None] ** j * d[:, None] ** (n - j)
    sign = 1.0 if kind == "call" else -1.0
    v = np.maximum(sign * (st - K[:, None]), 0)
    pc = p[:, None]
    for i in range(n - 1, -1, -1):
        j = np.arange(i + 1)
        st = S[:, None] * u[:, None] ** j * d[:, None] ** (i - j)
        v = disc * (pc * v[:, 1:] + (1 - pc) * v[:, :-1])
        v = np.maximum(v, sign * (st - K[:, None]))
    return v[:, 0]


def exercise_boundary(S, K, T, r, q, sigma, n=1000, kind="put"):
    """For one CRR tree of n steps: per step, the highest stock price where an American put is
    exercised (lowest for a call), NaN where no node is. Returns (time from today, boundary)."""
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    disc = np.exp(-r * dt)
    sign = 1.0 if kind == "call" else -1.0
    v = np.maximum(sign * (S * u ** np.arange(n + 1) * d ** (n - np.arange(n + 1)) - K), 0)
    edge = np.full(n + 1, np.nan)
    for i in range(n - 1, -1, -1):
        st = S * u ** np.arange(i + 1) * d ** (i - np.arange(i + 1))
        hold = disc * (p * v[1:] + (1 - p) * v[:-1])
        ex = sign * (st - K)
        go = (ex > hold + 1e-12 * K) & (ex > 0)
        v = np.where(go, ex, hold)
        if go.any():
            edge[i] = st[go].max() if kind == "put" else st[go].min()
    return np.arange(n + 1) * dt, edge
