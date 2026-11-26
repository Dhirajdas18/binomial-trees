"""Real NIFTY option cases from the sibling implied-vol-surface repo's local data (not committed
here either): its daily SVI table and NSE option rows. Set BTREE_IV_DIR to that repo
(default ~/quant-learn/implied-vol-surface).

`month_end_quotes`: on the last trading day of each month, every traded out-of-the-money NIFTY
option (puts below the forward, calls at or above) on expiries 7-365 days out, inside its slice's
quoted range, with that slice's forward F, time T and SVI volatility at the strike. Pricing on the
forward (S = F, q = r) gives Black-76, the market-consistent price for that volatility.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

R = 0.065  # the rate implied-vol-surface uses


def iv_dir() -> Path:
    return Path(os.environ.get("BTREE_IV_DIR", Path.home() / "quant-learn" / "implied-vol-surface"))


def svi_vol(row, k):
    a, b, rho, m, s = (row[x] for x in ("a", "b", "rho", "m", "sigma"))
    w = a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + s * s))
    return np.sqrt(np.maximum(w, 1e-12) / row["T"])


def month_end_quotes(min_days: int = 7) -> pd.DataFrame:
    base = iv_dir() / "data"
    svi = pd.read_parquet(base / "derived" / "svi_daily.parquet")
    svi = svi[svi["converged"] & (svi["days"] >= min_days)]
    dates = pd.DatetimeIndex(sorted(svi["date"].unique()))
    ends = set(pd.Series(dates, index=dates).groupby([dates.year, dates.month]).max())
    svi = svi[svi["date"].isin(ends)]
    opts = pd.read_parquet(base / "options" / "nifty_options.parquet",
                           columns=["date", "expiry", "strike", "type", "contracts"],
                           filters=[("date", "in", sorted(ends))])
    opts = opts[opts["contracts"] > 0].drop_duplicates(["date", "expiry", "strike", "type"])
    q = opts.merge(svi, on=["date", "expiry"])
    q["k"] = np.log(q["strike"] / q["F"])
    otm = ((q["type"] == "PE") & (q["strike"] < q["F"])) | ((q["type"] == "CE")
                                                          & (q["strike"] >= q["F"]))
    q = q[otm & q["k"].between(q["k_lo"], q["k_hi"])].copy()
    q["vol"] = svi_vol(q, q["k"])
    q["kind"] = np.where(q["type"] == "CE", "call", "put")
    return q[["date", "expiry", "days", "T", "F", "strike", "k", "kind", "vol"]].reset_index(
        drop=True)
