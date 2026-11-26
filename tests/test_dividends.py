import numpy as np
import pandas as pd

from btree import batch
from btree.dividends import american_escrowed, events, yield_shortcut


def test_no_dividend_matches_the_plain_tree():
    am, eu = american_escrowed(100, 95, 0.2, 0.065, 0.3, [], 201, "call")
    a = ([100.0], [95.0], [0.2], 0.065, 0.0, [0.3])
    assert np.isclose(am, batch.american(*a, 201, "call", "lr")[0])
    assert np.isclose(eu, batch.lr_european(*a, 201, "call")[0])


def test_european_prices_agree_and_the_yield_shortcut_misses_exercise_before_the_ex_date():
    divs = [(30 / 365, 5.0)]
    am, eu = american_escrowed(100, 90, 40 / 365, 0.065, 0.25, divs, 201, "call")
    ya, ye = yield_shortcut(100, 90, 40 / 365, 0.065, 0.25, divs, 201, "call")
    assert np.isclose(eu, ye)
    assert am > ya + 0.5 and am >= 10  # exercising just before the ex-date beats both


def test_events_strike_30_days_before_and_expire_10_after():
    idx = pd.bdate_range("2023-01-02", "2023-12-29")
    close = pd.Series(100 * np.exp(np.cumsum(np.full(len(idx), 0.0005))), index=idx)
    div = pd.Series(0.0, index=idx)
    ex = pd.Timestamp("2023-09-15")
    div.loc[ex] = 2.0
    ev = events({"ABC": pd.DataFrame({"close": close, "dividend": div})})
    r = ev.iloc[0]
    assert r["start"] == close.index[close.index <= ex - pd.Timedelta(days=30)][-1]
    assert np.isclose(r["T"], ((ex - r["start"]).days + 10) / 365)
    assert np.isclose(r["div_yield"], 2.0 / close.loc[r["start"]])
    assert r["divs"] == [((ex - r["start"]).days / 365, 2.0)]
