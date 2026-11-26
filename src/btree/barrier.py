"""Down-and-out calls: the option dies if the price touches the barrier H (below today's price).

- `dao_closed`: continuous monitoring, the closed form (Reiner-Rubinstein / Haug), for H <= K
  and H > K.
- `dao_crr`: a CRR tree that kills every node at or below H at every step. The barrier usually
  falls between two node levels, so the tree acts as if the barrier were at the next level down,
  which moves with n: the price saws up and down as n grows.
- `dao_trinomial`: Ritchken's trinomial tree, its spacing stretched (lambda >= 1) so that a row
  of nodes lies exactly on the barrier. `monitor` = how many steps between barrier checks
  (1 = every step; steps_per_day to check once a day).
- `bgk_barrier`: Broadie-Glasserman-Kou's correction: a barrier checked every dt behaves like a
  continuous one moved away by e^{-0.5826 sigma sqrt(dt)} (down barrier).
"""

import math

import numpy as np
from scipy.special import ndtr

BETA = 0.5826  # -zeta(1/2) / sqrt(2 pi), Broadie-Glasserman-Kou


def _bs_call(S, K, T, r, q, v):
    d1 = (math.log(S / K) + (r - q + 0.5 * v * v) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    return S * math.exp(-q * T) * ndtr(d1) - K * math.exp(-r * T) * ndtr(d2)


def dao_closed(S, K, H, T, r, q, v):
    """Down-and-out call, continuous barrier H < S (no rebate)."""
    if S <= H:
        return 0.0
    mu = (r - q - 0.5 * v * v) / (v * v)
    vt = v * math.sqrt(T)
    lam = mu + 1
    ef, er = math.exp(-q * T), math.exp(-r * T)

    def term(y):  # S e^{-qT} (H/S)^{2 lam} N(y) - K e^{-rT} (H/S)^{2 mu} N(y - vt)
        return S * ef * (H / S) ** (2 * lam) * ndtr(y) - K * er * (H / S) ** (2 * mu) * ndtr(y - vt)

    if H <= K:
        y = math.log(H * H / (S * K)) / vt + lam * vt
        return _bs_call(S, K, T, r, q, v) - term(y)
    x1 = math.log(S / H) / vt + lam * vt
    y1 = math.log(H / S) / vt + lam * vt
    a = S * ef * ndtr(x1) - K * er * ndtr(x1 - vt)
    return a - term(y1)


def dao_crr(S, K, H, T, r, q, v, n):
    dt = T / n
    u = math.exp(v * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    disc = math.exp(-r * dt)
    j = np.arange(n + 1)
    st = S * u**j * d ** (n - j)
    val = np.where(st > H, np.maximum(st - K, 0), 0.0)
    for i in range(n - 1, -1, -1):
        j = np.arange(i + 1)
        st = S * u**j * d ** (i - j)
        val = disc * (p * val[1:] + (1 - p) * val[:-1])
        val[st <= H] = 0.0
    return float(val[0])


def dao_trinomial(S, K, H, T, r, q, v, n, monitor=1):
    """Ritchken trinomial with a node row on the barrier; barrier checked every `monitor` steps."""
    dt = T / n
    dist = math.log(S / H)
    m = max(1, math.floor(dist / (v * math.sqrt(dt))))  # node rows between S and H
    dx = dist / m  # >= v sqrt(dt), so lambda = dx / (v sqrt dt) >= 1
    nu = r - q - 0.5 * v * v
    pu = 0.5 * (v * v * dt / dx**2) + 0.5 * nu * dt / dx
    pd = 0.5 * (v * v * dt / dx**2) - 0.5 * nu * dt / dx
    pm = 1 - pu - pd
    if min(pu, pd, pm) < 0:
        raise ValueError("trinomial probabilities out of range; use more steps")
    disc = math.exp(-r * dt)
    k = np.arange(-n, n + 1)
    st = S * np.exp(k * dx)
    val = np.where(st > H * (1 + 1e-12), np.maximum(st - K, 0), 0.0)
    for i in range(n - 1, -1, -1):
        val = disc * (pu * val[2:] + pm * val[1:-1] + pd * val[:-2])
        k = np.arange(-i, i + 1)
        if i % monitor == 0:
            val[S * np.exp(k * dx) <= H * (1 + 1e-12)] = 0.0
    return float(val[0])


def bgk_barrier(H, v, dt):
    """Continuous-equivalent of a down barrier H checked every dt (years)."""
    return H * math.exp(-BETA * v * math.sqrt(dt))
