"""Cash dividends on NSE stocks: Yahoo's history, and trees that pay them on their dates.

`fetch`: daily close (split-adjusted, not dividend-adjusted) and cash dividends from Yahoo for
each symbol (`<symbol>.NS`), one ticker at a time without threads, retried until every ticker has
data or the attempts run out; cached under data/ (not committed).

Escrowed-dividend tree: the dividends to be paid before expiry are taken out of today's price
(S* = S - their present value), S* follows the tree, and at each node the stock is S* plus the
present value of the dividends still to come. Exercise compares against that stock price, so an
American call can be exercised just before an ex-date. The "yield shortcut" instead spreads the
same present value over the option's life as a continuous yield q with S e^{-qT} = S*.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd

from btree import batch

CACHE = Path(__file__).resolve().parents[2] / "data" / "yahoo"


def fetch(symbols, start="2014-01-01", attempts=4, pause=1.0) -> dict[str, pd.DataFrame]:
    """{symbol: DataFrame(close, dividend)} from Yahoo, cached per symbol."""
    import yfinance as yf

    CACHE.mkdir(parents=True, exist_ok=True)
    out, todo = {}, []
    for s in symbols:
        f = CACHE / f"{s}.parquet"
        if f.exists():
            out[s] = pd.read_parquet(f)
        else:
            todo.append(s)
    for _ in range(attempts):
        missing = []
        for s in todo:
            try:
                h = yf.Ticker(f"{s}.NS").history(start=start, auto_adjust=False, actions=True)
            except Exception:  # noqa: BLE001 - network or parse errors: retry later
                h = pd.DataFrame()
            if h.empty or "Close" not in h:
                missing.append(s)
                continue
            df = pd.DataFrame({"close": h["Close"], "dividend": h.get("Dividends", 0.0)})
            df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
            df.to_parquet(CACHE / f"{s}.parquet")
            out[s] = df
            time.sleep(0.2)
        if not missing:
            break
        todo = missing
        time.sleep(pause * 5)
    return out


def american_escrowed(S, K, T, r, sigma, divs, n=201, kind="call", method="lr"):
    """American price with cash dividends `divs` = [(time, amount), ...] paid before expiry, on an
    escrowed-dividend tree (scalar inputs). Also returns the European price on the same tree."""
    from btree.batch import _params

    pv = sum(D * np.exp(-r * t) for t, D in divs if 0 < t < T)
    s_star = S - pv
    n, u, d, p = (np.asarray(x).item() if np.ndim(x) else x
                  for x in _params(np.array([s_star]), np.array([K]), np.array([T]), r, 0.0,
                                   np.array([sigma]), n, method))
    dt = T / n
    disc = np.exp(-r * dt)
    sign = 1.0 if kind == "call" else -1.0

    def to_come(t):
        return sum(D * np.exp(-r * (td - t)) for td, D in divs if t < td < T)

    j = np.arange(n + 1)
    v = np.maximum(sign * (s_star * u**j * d ** (n - j) - K), 0)
    e = v.copy()
    for i in range(n - 1, -1, -1):
        j = np.arange(i + 1)
        st = s_star * u**j * d ** (i - j) + to_come(i * dt)
        v = disc * (p * v[1:] + (1 - p) * v[:-1])
        v = np.maximum(v, sign * (st - K))
        e = disc * (p * e[1:] + (1 - p) * e[:-1])
    return float(v[0]), float(e[0])


def yield_shortcut(S, K, T, r, sigma, divs, n=201, kind="call"):
    """American and European prices with the same dividends spread as a continuous yield."""
    pv = sum(D * np.exp(-r * t) for t, D in divs if 0 < t < T)
    q = -np.log(1 - pv / S) / T
    a = ([S], [K], [T], r, q, [sigma])
    return (float(batch.american(*a, n, kind, "lr")[0]), float(batch.lr_european(*a, n, kind)[0]))


def events(data: dict[str, pd.DataFrame], before: int = 30, after: int = 10,
           vol_days: int = 60) -> pd.DataFrame:
    """One row per dividend: the option is struck `before` calendar days ahead of the ex-date
    (the last trading day on or before then), expires `after` days after it; spot = that day's
    close, volatility = the previous `vol_days` daily log returns' standard deviation x sqrt(252),
    dividend yield of the payment = amount / spot. Other dividends inside the window are kept."""
    rows = []
    for sym, df in data.items():
        c = df["close"].dropna()
        lr = np.log(c).diff()
        for ex, amt in df.loc[df["dividend"] > 0, "dividend"].items():
            start = c.index[c.index <= ex - pd.Timedelta(days=before)]
            if len(start) == 0:
                continue
            t0 = start[-1]
            past = lr.loc[:t0].dropna().iloc[-vol_days:]
            if len(past) < vol_days * 0.8:
                continue
            T = ((ex - t0).days + after) / 365
            window = df.loc[(df.index > t0) & (df.index <= t0 + pd.Timedelta(days=T * 365))
                            & (df["dividend"] > 0), "dividend"]
            divs = [((d - t0).days / 365, float(a)) for d, a in window.items()]
            rows.append({"symbol": sym, "ex_date": ex, "start": t0, "S": float(c.loc[t0]),
                         "dividend": float(amt), "vol": float(past.std() * np.sqrt(252)),
                         "T": T, "divs": divs})
    cols = ["symbol", "ex_date", "start", "S", "dividend", "vol", "T", "divs"]
    out = pd.DataFrame(rows, columns=cols)
    out["div_yield"] = out["dividend"] / out["S"]
    return out
