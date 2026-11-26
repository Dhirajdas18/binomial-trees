"""README findings, one function per topic: `btree report <topic>` writes charts to out/."""

from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from btree import plots

TICK = 0.05  # NSE's price step for options, in rupees


def _price_all(q, meth, n):
    """Tree prices of every quote in `q` (on the forward: S = F, q = r) with method `meth`."""
    from btree import batch
    from btree.data import R

    out = np.empty(len(q))
    for kind in ("call", "put"):
        idx = np.flatnonzero((q["kind"] == kind).to_numpy())
        for c in np.array_split(idx, max(1, len(idx) // 1500)):
            a = (q["F"].to_numpy()[c], q["strike"].to_numpy()[c], q["T"].to_numpy()[c], R, R,
                 q["vol"].to_numpy()[c])
            if meth == "bs":
                out[c] = batch.bs_european(*a, kind)
            elif meth == "crr":
                out[c] = batch.crr_european(*a, n, kind)
            elif meth == "avg":
                out[c] = 0.5 * (batch.crr_european(*a, n, kind)
                                + batch.crr_european(*a, n + 1, kind))
            else:
                out[c] = batch.lr_european(*a, n, kind)
    return out


def report_convergence(out_dir: Path) -> dict:
    """From one step to many: how fast CRR, CRR averaged over n and n+1 steps, and Leisen-Reimer
    reach the Black-Scholes price, for two example options and for every traded out-of-the-money
    NIFTY option on the last trading day of each month 2015-2026 (priced on the forward with the
    day's SVI volatility at its strike, so Black-76 is the target). Needs implied-vol-surface's
    local data (BTREE_IV_DIR)."""
    import pandas as pd

    from btree import batch
    from btree.data import R, month_end_quotes

    res = {}
    # One step, by hand: S 100, up 10% or down 10%, r 0 -> p = 0.5, call(100) = 5 by replication
    S, u, d = 100.0, 1.1, 1 / 1.1
    delta = (S * u - 100) / (S * u - S * d)
    bond = -delta * S * d  # delta shares plus this cash pays 10 if up and 0 if down
    p = (1 - d) / (u - d)
    res["one step by hand (S 100, up x1.1 or down /1.1, strike 100, no interest)"] = (
        f"replicate with {delta:.4f} shares and Rs {-bond:.2f} borrowed: cost "
        f"{delta * S + bond:.4f}; risk-neutral up chance (1 - d)/(u - d) = {p:.4f}; "
        f"p x payoff = {p * (S * u - 100):.4f}"
    )

    examples = {"at the money, 30 days": (25000.0, 25000.0, 30 / 365, 0.15, "call"),
                "10% out of the money put, 30 days": (25000.0, 22500.0, 30 / 365, 0.18, "put")}
    ns = np.arange(5, 301)
    curves = {}
    for name, (F, K, T, v, kind) in examples.items():
        a = ([F], [K], [T], R, R, [v])
        bs = float(batch.bs_european(*a, kind)[0])
        c = np.array([batch.crr_european(*a, n, kind)[0] for n in ns]) - bs
        av = 0.5 * (c[:-1] + c[1:])
        lr = np.array([batch.lr_european(*a, n, kind)[0] for n in ns]) - bs
        curves[name] = (c, av, lr, bs)
        at = {n: (c[n - 5], av[n - 5], lr[n - 5]) for n in (50, 100, 200)}
        res[f"{name}: Black-Scholes Rs {bs:.2f}; error at 50 / 100 / 200 steps"] = "; ".join(
            f"{n}: CRR {e[0]:+.3f}, averaged {e[1]:+.3f}, Leisen-Reimer {e[2]:+.4f}"
            for n, e in at.items())

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=False)
    for ax, (name, (c, av, lr, bs)) in zip(axes, curves.items(), strict=True):
        odd = ns % 2 == 1  # CRR's error flips sign between odd and even step counts at the money
        ax.plot(ns[odd], c[odd], color=plots.COLORS["CRR"], lw=1.6,
                label="basic tree (CRR), odd steps")
        ax.plot(ns[~odd], c[~odd], color=plots.BLUE_RAMP[2], lw=1.6, ls="--",
                label="basic tree (CRR), even steps")
        ax.plot(ns[:-1], av, color=plots.COLORS["averaged"], lw=1.8,
                label="average of n and n+1 steps")
        ax.plot(ns, lr, color=plots.COLORS["Leisen-Reimer"], lw=2, label="Leisen-Reimer")
        ax.axhline(0, color=plots.TEXT_2, lw=0.8)
        ax.axhspan(-TICK, TICK, color=plots.GRID, zorder=0)
        ax.set_ylim(-3, 3)
        ax.set_title(f"{name} (worth Rs {bs:,.0f})", fontsize=10.5)
        ax.set_xlabel("steps in the tree")
    axes[0].set_ylabel("tree price minus Black-Scholes, Rs\n(shaded: within one tick, Rs 0.05)")
    axes[0].legend(fontsize=8.5, loc="lower right")
    fig.suptitle("The basic tree zig-zags towards the right price; Leisen-Reimer lands on it",
                 x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout()
    plots.save(fig, out_dir, "convergence")
    plt.close(fig)

    q = month_end_quotes()
    bs = _price_all(q, "bs", 0)
    res["real NIFTY options"] = (
        f"{len(q):,} traded out-of-the-money options on {q['date'].nunique()} month-ends "
        f"({q['date'].min():%b %Y}-{q['date'].max():%b %Y}), 7-365 days; Black-76 price median "
        f"Rs {np.median(bs):.1f}"
    )
    steps = {"crr": (10, 25, 50, 100, 200, 500, 1000, 2000),
             "avg": (10, 25, 50, 100, 200, 500, 1000, 2000), "lr": (5, 11, 25, 51, 101, 201)}
    names = {"crr": "basic tree (CRR)", "avg": "average of n and n+1 steps",
             "lr": "Leisen-Reimer"}
    share = {}
    for m, nl in steps.items():
        share[m] = {}
        for n in nl:
            e = np.abs(_price_all(q, m, n) - bs)
            share[m][n] = (e <= TICK).mean()
            if n == 100 and m == "crr":
                crr100 = e
            if n == 100 and m == "avg":
                avg100 = e
            res[f"  {names[m]}, {n} steps"] = (
                f"within one tick {share[m][n]:.1%}; error median Rs {np.median(e):.4f}, "
                f"99th percentile Rs {np.quantile(e, 0.99):.3f}, largest Rs {e.max():.2f}"
            )
    b = pd.cut(q["k"].abs(), [0, 0.02, 0.05, 0.1, 0.2, 2],
               labels=["within 2%", "2-5%", "5-10%", "10-20%", "beyond 20%"])
    g = pd.DataFrame({"crr": crr100, "avg": avg100, "b": b}).groupby("b", observed=True).median()
    res["  100 steps, median error by distance from the forward: CRR / averaged"] = "; ".join(
        f"{k} Rs {r['crr']:.3f} / {r['avg']:.3f}" for k, r in g.iterrows())

    fig, ax = plt.subplots(figsize=(10, 4.2))
    for m in ("crr", "avg", "lr"):
        xs = list(share[m])
        ys = [100 * share[m][n] for n in xs]
        col = {"crr": plots.COLORS["CRR"], "avg": plots.COLORS["averaged"],
               "lr": plots.COLORS["Leisen-Reimer"]}[m]
        ax.plot(xs, ys, color=col, lw=2, marker="o", ms=4)
        nudge = {"crr": -6, "avg": 2, "lr": 0}[m]  # keep the two right-hand labels apart
        plots.label_line_end(ax, xs[-1], ys[-1] + nudge, names[m], col)
    ax.set_xscale("log")
    ax.set_xticks([5, 10, 25, 50, 100, 200, 500, 1000, 2000],
                  ["5", "10", "25", "50", "100", "200", "500", "1,000", "2,000"])
    ax.set_xlim(4, 9000)
    ax.set_ylim(0, 102)
    ax.set_xlabel("steps in the tree")
    ax.set_ylabel("real NIFTY options priced\nwithin one tick (Rs 0.05), %")
    ax.set_title("Leisen-Reimer priced every NIFTY option to the tick by 51 steps; the basic tree "
                 "needed thousands", fontsize=12)
    fig.tight_layout()
    plots.save(fig, out_dir, "convergence_real")
    plt.close(fig)
    return res


def _greeks_all(q, fn, *args, **kw):
    """Delta, gamma, theta for every quote (on the forward), with a batch Greek function."""
    from btree.data import R

    out = [np.empty(len(q)) for _ in range(3)]
    for kind in ("call", "put"):
        idx = np.flatnonzero((q["kind"] == kind).to_numpy())
        for c in np.array_split(idx, max(1, len(idx) // 1500)):
            a = (q["F"].to_numpy()[c], q["strike"].to_numpy()[c], q["T"].to_numpy()[c], R, R,
                 q["vol"].to_numpy()[c])
            for o, v in zip(out, fn(*a, *args, kind=kind, **kw), strict=True):
                o[c] = v
    return out


def report_greeks(out_dir: Path) -> dict:
    """Greeks from the tree against the Black-Scholes (Black-76) formulas on the real NIFTY
    options of finding 1: delta, gamma and theta read off the first two steps of CRR and
    Leisen-Reimer trees, Leisen-Reimer's theta moved back to today's price, and Leisen-Reimer
    re-priced with the price moved +-0.5% and one day later."""
    from btree import batch
    from btree.data import month_end_quotes

    res = {}
    q = month_end_quotes()
    bd, bg, bt = _greeks_all(q, batch.bs_greeks)
    methods = {
        "basic tree, 100 steps": (batch.node_greeks, (100,), {"method": "crr"}),
        "basic tree, 500 steps": (batch.node_greeks, (500,), {"method": "crr"}),
        "Leisen-Reimer nodes, 101 steps": (batch.node_greeks, (101,), {"method": "lr"}),
        "Leisen-Reimer nodes, theta moved to today": (batch.node_greeks, (101,),
                                                      {"method": "lr", "correct": True}),
        "Leisen-Reimer re-priced (101 steps)": (batch.bump_greeks, (101,), {}),
    }
    res["options"] = f"{len(q):,} (finding 1's month-end NIFTY options)"
    med = {}
    for name, (fn, args, kw) in methods.items():
        d, g, t = _greeks_all(q, fn, *args, **kw)
        de = 100 * np.abs(d - bd)
        ge = 100 * np.abs(g / bg - 1)
        te = 100 * np.abs(t / bt - 1)
        med[name] = (np.median(de), np.median(ge), np.median(te))
        res[f"  {name}"] = (
            f"delta error median {np.median(de):.4f} points (99th percentile "
            f"{np.quantile(de, 0.99):.3f}); gamma error median {np.median(ge):.2f}% (within 1%: "
            f"{(ge < 1).mean():.0%}); theta error median {np.median(te):.2f}% "
            f"(Rs {np.median(np.abs(t - bt)) / 365:.4f} a day)"
        )

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.4))
    names = list(methods)
    short = ["basic\n100", "basic\n500", "LR\nnodes", "LR nodes\ntheta\nfixed",
             "LR\nre-priced"]
    cols = [plots.COLORS["CRR"], plots.BLUE_RAMP[5], plots.COLORS["Leisen-Reimer"],
            plots.SERIES[4], plots.SERIES[3]]  # green means "averaged" elsewhere
    titles = ("delta, error in points", "gamma, error in %", "theta, error in %")
    for j, ax in enumerate(axes):
        vals = [med[nm][j] for nm in names]
        ax.bar(range(len(names)), vals, color=cols)
        ax.set_yscale("log")
        for x, y in enumerate(vals):
            ax.text(x, y * 1.15, f"{y:.3g}", ha="center", va="bottom", fontsize=8.5,
                    color=plots.TEXT)
        ax.set_xticks(range(len(names)), short, fontsize=8.5)
        ax.set_title(titles[j], fontsize=10.5)
        ax.set_ylim(min(vals) / 3, max(vals) * 4)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_minor_formatter(plt.NullFormatter())
    axes[0].set_ylabel("median error against the formula\n(log scale; 37,652 NIFTY options)")
    fig.suptitle("Read Greeks off a basic tree or re-price; Leisen-Reimer's own nodes give a "
                 "wrong theta", x=0.01, ha="left", fontsize=12.5, fontweight="semibold")
    fig.tight_layout()
    plots.save(fig, out_dir, "greeks")
    plt.close(fig)
    return res


NIFTY_YIELD = 0.013  # median dividend yield implied by NIFTY forwards against its close, 2015-2026


def report_american(out_dir: Path) -> dict:
    """American options: what early exercise would add to the real NIFTY options of finding 1 if
    they were American (they are European on NSE), priced on NIFTY's close with a 1.3% dividend
    yield and the day's volatility at each strike, 201-step Leisen-Reimer trees; how the premium
    of an at-the-money put depends on the interest rate; and the early-exercise boundary.
    Needs BTREE_IV_DIR (options) and IV_LAKE_DIR or BTREE_LAKE_DIR (NIFTY close)."""
    import os

    import pandas as pd

    from btree import batch
    from btree.data import R, month_end_quotes

    res = {}
    lake = Path(os.environ.get("BTREE_LAKE_DIR") or os.environ.get("IV_LAKE_DIR")
                or Path.home() / "data" / "lake")
    nifty = pd.read_parquet(lake / "market.parquet").set_index("date")["nifty"]
    q = month_end_quotes().join(nifty.rename("S"), on="date").dropna(subset=["S"])
    s_all = q.drop_duplicates(["date", "expiry"])
    implied_q = R - np.log(s_all["F"] / s_all["S"]) / s_all["T"]
    res["dividend yield"] = (
        f"{NIFTY_YIELD:.1%} for every option: the median of {implied_q.median():.2%} implied by "
        f"each expiry's forward against NIFTY's close ({len(s_all)} expiries; 5th-95th percentile "
        f"{implied_q.quantile(0.05):.1%} to {implied_q.quantile(0.95):.1%}, noisy because the "
        f"close and the option prices are not taken at the same moment)"
    )
    am, eu = np.empty(len(q)), np.empty(len(q))
    for kind in ("call", "put"):
        idx = np.flatnonzero((q["kind"] == kind).to_numpy())
        for c in np.array_split(idx, max(1, len(idx) // 1500)):
            a = (q["S"].to_numpy()[c], q["strike"].to_numpy()[c], q["T"].to_numpy()[c], R,
                 NIFTY_YIELD, q["vol"].to_numpy()[c])
            am[c] = batch.american(*a, 201, kind, "lr")
            eu[c] = batch.lr_european(*a, 201, kind)
    # American >= European; differences below zero are rounding (about 1e-12)
    q = q.assign(prem=np.maximum(am - eu, 0), eu=eu, m=q["strike"] / q["S"])
    for kind, g in q.groupby("kind"):
        res[f"{kind}s ({len(g):,})"] = (
            f"early-exercise premium worth over one tick for {(g['prem'] > TICK).mean():.1%}; "
            f"median Rs {g['prem'].median():.2f} ({(g['prem'] / g['eu']).median():.2%} of the "
            f"European price), mean Rs {g['prem'].mean():.2f}, largest Rs {g['prem'].max():.0f}"
        )
    p = q[q["kind"] == "put"]
    mb = pd.cut(p["m"], [0, 0.9, 0.95, 1.0, 10],
                labels=["strike over 10% below NIFTY", "5-10% below", "0-5% below",
                        "above NIFTY"])
    gm = p.groupby(mb, observed=True)
    res["  puts by strike against NIFTY's close"] = "; ".join(
        f"{k}: {len(gg):,}, median Rs {gg['prem'].median():.2f} "
        f"({(gg['prem'] / gg['eu']).median():.2%}), over a tick {(gg['prem'] > TICK).mean():.0%}"
        for k, gg in gm)
    db = pd.cut(p["days"], [0, 15, 35, 90, 400], labels=["7-15 days", "16-35", "36-90", "91-365"])
    res["  puts by days to expiry"] = "; ".join(
        f"{k}: median Rs {gg['prem'].median():.2f} ({(gg['prem'] / gg['eu']).median():.2%})"
        for k, gg in p.groupby(db, observed=True))

    rates = np.linspace(0, 0.12, 25)
    curves = {}
    for days in (30, 91, 365):
        T = days / 365
        am_r = np.array([batch.american([25000.0], [25000.0], [T], r, NIFTY_YIELD, [0.15], 201,
                                        "put", "lr")[0] for r in rates])
        eu_r = np.array([batch.lr_european([25000.0], [25000.0], [T], r, NIFTY_YIELD, [0.15], 201,
                                           "put")[0] for r in rates])
        curves[days] = 100 * np.maximum(am_r - eu_r, 0) / eu_r
        at = (0, int(np.argmin(np.abs(rates - 0.065))), len(rates) - 1)
        res[f"at-the-money put, {days} days, 15% vol: premium, % of European, rate 0/6.5%/12%"] = (
            " / ".join(f"{curves[days][i]:.2f}%" for i in at))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    ax = axes[0]
    for vol, col in ((0.12, plots.BLUE_RAMP[3]), (0.18, plots.BLUE_RAMP[5]),
                     (0.25, plots.SERIES[1])):
        t, e = batch.exercise_boundary(25000.0, 25000.0, 1.0, R, NIFTY_YIELD, vol, 2000)
        left = (1.0 - t) * 365
        ok = np.isfinite(e)
        # the boundary jumps between neighbouring node levels; smooth over 41 steps (~1 week)
        xs = left[ok]
        ys = (pd.Series(100 * e[ok] / 25000).rolling(41, center=True, min_periods=1).mean()
              .to_numpy())
        ax.plot(xs, ys, color=col, lw=2)
        plots.label_line_end(ax, xs[0], ys[0], f"volatility {vol:.0%}", col)
        res[f"exercise boundary, 1-year put, {vol:.0%} vol"] = (
            f"exercise once NIFTY is below {100 * e[ok][0] / 25000:.1f}% of the strike a year out, "
            f"{100 * np.interp(30, left[ok][::-1], e[ok][::-1]) / 25000:.1f}% with 30 days left"
        )
    ax.invert_xaxis()
    ax.set_xlim(380, -5)
    ax.set_xlabel("days left to expiry")
    ax.set_ylabel("exercise a put early once NIFTY\nfalls below this % of the strike")
    ax.set_title("Where early exercise starts (put, rate 6.5%)", fontsize=10.5)
    ax = axes[1]
    for days, col in ((30, plots.BLUE_RAMP[3]), (91, plots.BLUE_RAMP[5]), (365, plots.SERIES[1])):
        ax.plot(100 * rates, curves[days], color=col, lw=2)
        plots.label_line_end(ax, 100 * rates[-1], curves[days][-1], f"{days} days", col)
    ax.axvline(100 * R, color=plots.TEXT_2, lw=0.8, ls="--")
    ax.set_xlim(0, 15)
    ax.set_xlabel("interest rate, % a year (dashed: 6.5%)")
    ax.set_ylabel("extra value of an at-the-money\nAmerican put, % of the European")
    ax.set_title("The right to exercise early is worth more when rates are high", fontsize=10.5)
    fig.suptitle("Early exercise of a NIFTY-like put pays only after a deep fall, and matters "
                 "more with time and high rates", x=0.01, ha="left", fontsize=12,
                 fontweight="semibold")
    fig.tight_layout()
    plots.save(fig, out_dir, "american")
    plt.close(fig)
    return res


def report_dividends(out_dir: Path) -> dict:
    """Cash dividends on NSE stocks: for every dividend Yahoo records for today's F&O stocks
    (2014-2026), a call struck 30 days before the ex-date and expiring 10 days after it, at the
    money and 10% in the money, on the day's close with the previous 60 days' volatility and a
    6.5% rate: American against European on an escrowed-dividend tree (201-step Leisen-Reimer),
    and the American price with the dividend spread as a continuous yield instead. Needs
    BTREE_IV_DIR (for today's F&O list); Yahoo data is fetched once and cached under data/."""
    import pandas as pd

    from btree.data import R, iv_dir
    from btree.dividends import american_escrowed, events, fetch, yield_shortcut

    res = {}
    so = pd.read_parquet(iv_dir() / "data" / "options" / "stock_options.parquet",
                         columns=["date", "symbol"])
    syms = sorted(so.loc[so["date"] == so["date"].max(), "symbol"].unique())
    data = fetch(syms)
    ev = events(data)
    res["dividends"] = (
        f"{len(ev):,} on {ev['symbol'].nunique()} of {len(syms)} current F&O stocks "
        f"({ev['ex_date'].min():%b %Y}-{ev['ex_date'].max():%b %Y}); size as % of the price: "
        f"median {ev['div_yield'].median():.2%}, 90th percentile "
        f"{ev['div_yield'].quantile(0.9):.2%}, "
        f"largest {ev['div_yield'].max():.1%}; volatility median {ev['vol'].median():.1%}"
    )
    rows = []
    for r in ev.itertuples():
        for m in (0.9, 1.0):
            K = r.S * m
            am, eu = american_escrowed(r.S, K, r.T, R, r.vol, r.divs, 201, "call")
            ya, ye = yield_shortcut(r.S, K, r.T, R, r.vol, r.divs, 201, "call")
            rows.append({"dy": r.div_yield, "m": m, "am": am, "eu": eu, "ya": ya, "ye": ye})
    d = pd.DataFrame(rows)
    d["prem"] = d["am"] - d["eu"]
    d["err"] = d["am"] - d["ya"]
    bins = [0, 0.005, 0.01, 0.02, 0.05, 1]
    labels = ["under 0.5%", "0.5-1%", "1-2%", "2-5%", "over 5%"]
    tab = {}
    for m, g in d.groupby("m"):
        name = "at the money" if m == 1.0 else "10% in the money"
        res[f"call {name}"] = (
            f"early exercise worth over a tick for {(g['prem'] > TICK).mean():.0%}; premium median "
            f"{(g['prem'] / g['eu']).median():.2%} of the European price; the yield shortcut "
            f"undervalues the American price by over a tick for {(g['err'] > TICK).mean():.0%}, "
            f"median {(g['err'] / g['am']).median():.2%} (90th percentile "
            f"{(g['err'] / g['am']).quantile(0.9):.1%}); European prices differ by at most "
            f"Rs {(g['eu'] - g['ye']).abs().max():.6f}"
        )
        gb = g.groupby(pd.cut(g["dy"], bins, labels=labels), observed=True)
        tab[m] = gb.apply(lambda x: pd.Series({
            "n": len(x), "prem": 100 * (x["prem"] / x["eu"]).median(),
            "err": 100 * (x["err"] / x["am"]).median()}), include_groups=False)
        res[f"  {name}, by dividend size: premium / shortcut error (median % )"] = "; ".join(
            f"{k} ({int(r_['n'])}): {r_['prem']:.1f}% / {r_['err']:.1f}%"
            for k, r_ in tab[m].iterrows())

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), sharey=False)
    xs = np.arange(len(labels))
    for ax, key, title in ((axes[0], "prem", "extra value of exercising early"),
                           (axes[1], "err", "how much the yield shortcut undervalues it")):
        for j, (m, col, lab) in enumerate(((1.0, plots.COLORS["CRR"], "at the money"),
                                           (0.9, plots.SERIES[1], "10% in the money"))):
            vals = tab[m][key].reindex(labels).to_numpy()
            ax.bar(xs + (j - 0.5) * 0.38, vals, 0.38, color=col, label=lab)
            for x, y in zip(xs + (j - 0.5) * 0.38, vals, strict=True):
                ax.text(x, y + 1, f"{y:.0f}%", ha="center", va="bottom", fontsize=8,
                        color=plots.TEXT)
        ax.set_xticks(xs, labels)
        ax.set_xlabel("dividend as % of the share price")
        ax.set_title(title, fontsize=10.5)
    axes[0].set_ylabel("median, % of the call's price")
    axes[0].legend(fontsize=9, loc="upper left")
    fig.suptitle("Big dividends make exercising a stock call early worth a lot, and a smooth "
                 "yield misses it", x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout()
    plots.save(fig, out_dir, "dividends")
    plt.close(fig)
    return res


REPORTS: dict[str, Callable[[Path], dict]] = {
    "convergence": report_convergence,
    "greeks": report_greeks,
    "american": report_american,
    "dividends": report_dividends,
}
