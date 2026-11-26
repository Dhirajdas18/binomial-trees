import math

import numpy as np
import pytest

from btree import tree as t

STD = (100.0, 100.0, 1.0, 0.05, 0.02, 0.2)  # spot, strike, years, rate, dividend yield, vol
NIFTY = (25000.0, 25000.0, 30 / 365, 0.065, 0.012, 0.15)


def test_one_step_tree_matches_replication_by_hand():
    S, K, T, r, q, sigma = 100.0, 100.0, 0.5, 0.05, 0.0, 0.3
    u = math.exp(sigma * math.sqrt(T))
    d = 1 / u
    cu, cd = S * u - K, 0.0
    # Hold delta shares and B in cash so the portfolio pays cu after an up move, cd after a down.
    delta = (cu - cd) / (S * u - S * d)
    B = math.exp(-r * T) * (cu - delta * S * u)
    assert t.crr(S, K, T, r, q, sigma, 1) == pytest.approx(delta * S + B, rel=1e-12)
    g = t.crr_tree(S, K, T, r, q, sigma, 1)
    assert g["value"][1].tolist() == pytest.approx([cd, cu])
    assert g["stock"][1].tolist() == pytest.approx([S * d, S * u])


@pytest.mark.parametrize("n", [1, 2, 7, 50, 301])
def test_european_tree_prices_obey_put_call_parity(n):
    S, K, T, r, q, sigma = STD
    c = t.crr(*STD, n, "call")
    p = t.crr(*STD, n, "put")
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-9)


@pytest.mark.parametrize("kind", ["call", "put"])
def test_crr_converges_to_black_scholes(kind):
    assert abs(t.crr(*STD, 2000, kind) - t.bs_price(*STD, kind)) < 0.01


def test_black_scholes_known_value():
    # Hull's example: S 42, K 40, r 10%, sigma 20%, 6 months: call 4.76, put 0.81.
    assert t.bs_price(42, 40, 0.5, 0.1, 0.0, 0.2, "call") == pytest.approx(4.7594, abs=1e-4)
    assert t.bs_price(42, 40, 0.5, 0.1, 0.0, 0.2, "put") == pytest.approx(0.8086, abs=1e-4)


@pytest.mark.parametrize("args", [STD, NIFTY])
def test_leisen_reimer_error_far_below_crr(args):
    bs = t.bs_price(*args, "call")
    lr = abs(t.leisen_reimer(*args, 101) - bs)
    crr = abs(t.crr(*args, 101) - bs)
    assert lr < crr / 50


def test_leisen_reimer_rounds_even_steps_up_to_odd():
    assert t.leisen_reimer(*STD, 100) == t.leisen_reimer(*STD, 101)


def test_averaged_tree_beats_plain_crr():
    bs = t.bs_price(*STD)
    assert abs(t.crr_averaged(*STD, 100) - bs) < abs(t.crr(*STD, 100) - bs) / 5
    assert t.crr_prices(*STD, [10, 11]).tolist() == [t.crr(*STD, 10), t.crr(*STD, 11)]


def test_american_put_at_least_european():
    for n in (5, 50, 200):
        assert t.crr(*STD, n, "put", american=True) >= t.crr(*STD, n, "put") - 1e-12


def test_american_call_equals_european_without_dividends():
    args = (100.0, 95.0, 1.0, 0.05, 0.0, 0.25)
    assert t.crr(*args, 200, "call", True) == pytest.approx(t.crr(*args, 200, "call"), abs=1e-10)
    assert not any(e.any() for e in t.crr_tree(*args, 30, "call", True)["exercise"])


def test_deep_in_the_money_american_put_carries_an_early_exercise_premium():
    args = (60.0, 100.0, 1.0, 0.08, 0.0, 0.2)
    amer, euro = t.crr(*args, 200, "put", True), t.crr(*args, 200, "put")
    assert amer - euro > 1.0
    assert amer == pytest.approx(40.0)  # exercise at once: K - S
    g = t.crr_tree(*args, 10, "put", True)
    assert g["exercise"][0][0] and not g["exercise"][-1].any()  # expiry is not "early"


def test_tree_arrays_are_consistent():
    g = t.crr_tree(*NIFTY, 6, "put", True)
    assert [len(s) for s in g["stock"]] == list(range(1, 8))
    assert g["value"][0][0] == pytest.approx(t.crr(*NIFTY, 6, "put", True), rel=1e-12)
    assert np.all(np.diff(g["stock"][6]) > 0)  # index j counts up moves
    assert g["stock"][2][1] == pytest.approx(NIFTY[0])  # u d = 1: the middle node is spot again


def test_tree_greeks_close_to_black_scholes():
    S, K, T, r, q, sigma = STD
    g = t.crr_greeks(*STD, 1000)
    d1 = (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    assert g["delta"] == pytest.approx(math.exp(-q * T) * t.norm.cdf(d1), abs=2e-3)
    gamma = math.exp(-q * T) * pdf / (S * sigma * math.sqrt(T))
    assert g["gamma"] == pytest.approx(gamma, rel=1e-2)
    assert g["theta"] < 0


def test_probability_out_of_range_raises():
    # One step over 10 years with 1% vol: the drift e^{(r-q)dt} overshoots u.
    with pytest.raises(ValueError, match="outside"):
        t.crr(100, 100, 10.0, 0.1, 0.0, 0.01, 1)
    with pytest.raises(ValueError):
        t.crr(100, 100, 1.0, 0.05, 0.0, 0.2, 0)
    with pytest.raises(ValueError):
        t.crr_tree(*STD, 51)
