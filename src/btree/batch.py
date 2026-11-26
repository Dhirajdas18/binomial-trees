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
