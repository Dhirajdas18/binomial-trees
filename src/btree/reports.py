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


REPORTS: dict[str, Callable[[Path], dict]] = {
    "convergence": report_convergence,
    "greeks": report_greeks,
}
