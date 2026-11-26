"""Binomial option-pricing trees: Cox-Ross-Rubinstein, its Greeks and convergence helpers, and
Leisen-Reimer, against Black-Scholes with a continuous dividend yield as the closed-form reference.

Conventions: S spot, K strike, T years to expiry, r and q continuously compounded rate and dividend
yield a year, sigma volatility a year, n time steps, kind "call" or "put".
"""

import math

import numpy as np
from scipy.stats import norm


def _check(S, K, T, sigma, n=None, kind="call") -> None:
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        raise ValueError("spot, strike, time to expiry and volatility must all be positive")
    if n is not None and (int(n) != n or n < 1):
        raise ValueError(f"steps must be a whole number of at least 1, got {n}")
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")


def _payoff(stock, K, kind):
    return np.maximum(stock - K, 0.0) if kind == "call" else np.maximum(K - stock, 0.0)


def bs_price(S, K, T, r, q, sigma, kind="call") -> float:
    """Black-Scholes(-Merton) price of a European option on a stock paying dividend yield q."""
    _check(S, K, T, sigma, kind=kind)
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    d2 = d1 - vt
    sign = 1.0 if kind == "call" else -1.0
    share_leg = S * math.exp(-q * T) * norm.cdf(sign * d1)
    return float(sign * (share_leg - K * math.exp(-r * T) * norm.cdf(sign * d2)))


def crr_params(T, r, q, sigma, n) -> tuple[float, float, float, float]:
    """(dt, u, d, p) for the CRR tree: u = e^{sigma sqrt(dt)}, d = 1/u,
    p = (e^{(r-q)dt} - d) / (u - d). Raises if p falls outside (0, 1)."""
    dt = T / n
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise ValueError(
            f"risk-neutral probability p = {p:.4f} is outside (0, 1): with {n} steps the drift "
            f"(r - q) is too large for the volatility; use more steps or a higher volatility"
        )
    return dt, u, d, p


def _induct(S, K, T, r, n, u, d, p, kind, american, keep):
    """Backward induction on a recombining tree with up factor u, down factor d and up
    probability p, one vectorised step at a time. Node j at step i has j up moves, so its stock
    price is S u^j d^(i-j). Returns {step: (stock, value, exercise)} for the steps below `keep`;
    exercise marks nodes before expiry where exercising beats holding (American only)."""
    disc = math.exp(-r * T / n)
    j = np.arange(n + 1)
    stock = S * u**j * d ** (n - j)
    value = _payoff(stock, K, kind)
    levels = {n: (stock, value, np.zeros(n + 1, bool))} if keep > n else {}
    tol = 1e-9 * K  # ignore exercise "gains" that are only rounding
    for i in range(n - 1, -1, -1):
        stock = S * u ** j[: i + 1] * d ** (i - j[: i + 1])
        value = disc * (p * value[1:] + (1 - p) * value[:-1])
        exercise = np.zeros(i + 1, bool)
        if american:
            intrinsic = _payoff(stock, K, kind)
            exercise = intrinsic > value + tol
            value = np.maximum(value, intrinsic)
        if i < keep:
            levels[i] = (stock, value, exercise)
    return levels


def crr(S, K, T, r, q, sigma, n, kind="call", american=False) -> float:
    """Price on an n-step Cox-Ross-Rubinstein tree; American takes max(hold, exercise) at
    every node."""
    _check(S, K, T, sigma, n, kind)
    _, u, d, p = crr_params(T, r, q, sigma, n)
    return float(_induct(S, K, T, r, n, u, d, p, kind, american, keep=1)[0][1][0])


def crr_tree(S, K, T, r, q, sigma, n, kind="call", american=False) -> dict:
    """The whole CRR tree for drawing (n <= 50): per step i, arrays over j = 0..i up moves of the
    stock price, the option value and whether early exercise is optimal there."""
    _check(S, K, T, sigma, n, kind)
    if n > 50:
        raise ValueError(f"crr_tree keeps every node; use at most 50 steps, got {n}")
    dt, u, d, p = crr_params(T, r, q, sigma, n)
    lv = _induct(S, K, T, r, n, u, d, p, kind, american, keep=n + 1)
    steps = range(n + 1)
    return {
        "dt": dt, "u": u, "d": d, "p": p,
        "stock": [lv[i][0] for i in steps],
        "value": [lv[i][1] for i in steps],
        "exercise": [lv[i][2] for i in steps],
    }


def crr_greeks(S, K, T, r, q, sigma, n, kind="call", american=False) -> dict:
    """Price, delta, gamma and theta (a year) from the tree itself (n >= 2): delta from the two
    step-1 nodes, gamma from the change in delta across the three step-2 nodes, theta from the
    step-2 middle node, which sits at today's spot (u d = 1), two steps (2 dt) later."""
    _check(S, K, T, sigma, n, kind)
    if n < 2:
        raise ValueError("tree Greeks need at least 2 steps")
    dt, u, d, p = crr_params(T, r, q, sigma, n)
    lv = _induct(S, K, T, r, n, u, d, p, kind, american, keep=3)
    (_, f0, _), (s1, f1, _), (s2, f2, _) = lv[0], lv[1], lv[2]
    # Index j counts up moves, so [1] is above [0].
    d_up = (f2[2] - f2[1]) / (s2[2] - s2[1])
    d_dn = (f2[1] - f2[0]) / (s2[1] - s2[0])
    return {
        "price": float(f0[0]),
        "delta": float((f1[1] - f1[0]) / (s1[1] - s1[0])),
        "gamma": float((d_up - d_dn) / (0.5 * (s2[2] - s2[0]))),
        "theta": float((f2[1] - f0[0]) / (2 * dt)),
    }


def crr_prices(S, K, T, r, q, sigma, ns, kind="call", american=False) -> np.ndarray:
    """CRR prices for each step count in ns (to watch the tree converge)."""
    return np.array([crr(S, K, T, r, q, sigma, n, kind, american) for n in ns])


def crr_averaged(S, K, T, r, q, sigma, n, kind="call", american=False) -> float:
    """The average of the n- and (n+1)-step CRR prices: CRR's error flips sign between odd and
    even n, so the average cancels most of the zigzag."""
    return 0.5 * (crr(S, K, T, r, q, sigma, n, kind, american)
                  + crr(S, K, T, r, q, sigma, n + 1, kind, american))


def _pp2(z, n):
    """Peizer-Pratt inversion, method 2: a binomial probability that matches N(z) on n steps."""
    x = z / (n + 1 / 3 + 0.1 / (n + 1))
    return 0.5 + math.copysign(math.sqrt(0.25 - 0.25 * math.exp(-x * x * (n + 1 / 6))), z)


def lr_params(S, K, T, r, q, sigma, n) -> tuple[int, float, float, float]:
    """(n, u, d, p) for the Leisen-Reimer tree; an even n is raised to the next odd number."""
    n = n if n % 2 else n + 1
    dt = T / n
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    d2 = d1 - vt
    p, p1 = _pp2(d2, n), _pp2(d1, n)
    g = math.exp((r - q) * dt)
    u = g * p1 / p
    d = (g - p * u) / (1 - p)
    return n, u, d, p


def leisen_reimer(S, K, T, r, q, sigma, n, kind="call", american=False) -> float:
    """Leisen-Reimer price (Peizer-Pratt method 2, odd n; an even n uses n + 1). The tree is
    centred on the strike, so the European price converges smoothly and about as 1/n^2."""
    _check(S, K, T, sigma, n, kind)
    n, u, d, p = lr_params(S, K, T, r, q, sigma, n)
    return float(_induct(S, K, T, r, n, u, d, p, kind, american, keep=1)[0][1][0])
