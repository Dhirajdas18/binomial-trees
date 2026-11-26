import numpy as np
import pandas as pd

from btree import data


def test_month_end_quotes_keep_traded_out_of_the_money_strikes_inside_the_quoted_range(
        tmp_path, monkeypatch):
    (tmp_path / "data" / "derived").mkdir(parents=True)
    (tmp_path / "data" / "options").mkdir(parents=True)
    d1, d2, e = pd.Timestamp("2024-01-30"), pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")
    svi = pd.DataFrame([{"date": d, "expiry": e, "days": (e - d).days, "T": (e - d).days / 365,
                         "F": 100.0, "a": 0.002, "b": 0.0, "rho": 0.0, "m": 0.0, "sigma": 0.1,
                         "k_lo": -0.1, "k_hi": 0.1, "converged": True} for d in (d1, d2)])
    svi.to_parquet(tmp_path / "data" / "derived" / "svi_daily.parquet")
    rows = [(d2, 95, "PE", 10), (d2, 95, "CE", 10), (d2, 105, "CE", 10), (d2, 105, "PE", 10),
            (d2, 80, "PE", 10), (d2, 97, "PE", 0), (d1, 95, "PE", 10)]
    pd.DataFrame(rows, columns=["date", "strike", "type", "contracts"]).assign(expiry=e).to_parquet(
        tmp_path / "data" / "options" / "nifty_options.parquet")
    monkeypatch.setenv("BTREE_IV_DIR", str(tmp_path))
    q = data.month_end_quotes()
    # month-end only, traded, OTM (put 95, call 105), inside k in [-0.1, 0.1] (80 is outside)
    assert sorted(zip(q["strike"], q["kind"], strict=True)) == [(95, "put"), (105, "call")]
    assert np.allclose(q["vol"], np.sqrt(0.002 / q["T"]))
