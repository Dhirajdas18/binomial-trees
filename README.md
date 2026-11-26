# Binomial Trees

[![CI](https://github.com/Dhirajdas18/binomial-trees/actions/workflows/ci.yml/badge.svg)](https://github.com/Dhirajdas18/binomial-trees/actions/workflows/ci.yml)
[![Tree lab](https://github.com/Dhirajdas18/binomial-trees/actions/workflows/pages.yml/badge.svg)](https://dhirajdas18.github.io/binomial-trees/)

Binomial (and later trinomial) option-pricing trees, from a single up-or-down step to trees fitted
to the NIFTY smile: Cox-Ross-Rubinstein and its convergence to Black-Scholes, Greeks from the tree,
American early exercise, NSE dividends and barriers.

**Live tree lab: [dhirajdas18.github.io/binomial-trees](https://dhirajdas18.github.io/binomial-trees/)**,
set the share price, strike, volatility, days, rate and dividend yield, and see the tree itself
with the option value at every node, where early exercise pays, and how the tree price converges
to Black-Scholes as the steps grow; all computed in the browser.

## Features

- [x] One step to many: replication, risk-neutral probability, CRR and its convergence to Black-Scholes
- [ ] Greeks from the tree
- [ ] American options: the early-exercise premium and boundary
- [ ] Discrete cash dividends on NSE stocks
- [ ] Trinomial trees and barrier options
- [ ] An implied tree fitted to the NIFTY smile
- [ ] Does a smile-fitted tree hedge better than Black-Scholes

## Findings

### 1. Leisen-Reimer priced every NIFTY option to the tick by 51 steps; the basic tree needed thousands

<a href="docs/img/convergence.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/convergence.png"><img src="docs/img/convergence.gif" alt="Tree price minus Black-Scholes against the number of steps for an at-the-money call and a 10 percent out-of-the-money put: CRR odd and even steps, the n and n+1 average, and Leisen-Reimer" width="720"></picture></a>

<a href="docs/img/convergence_real.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/convergence_real.png"><img src="docs/img/convergence_real.gif" alt="Share of real NIFTY options priced within one tick by each tree, against the number of steps" width="720"></picture></a>

One step first: with the price going up ×1.1 or down ÷1.1 and a strike of 100, holding 0.5238
shares and borrowing ₹47.62 pays exactly what the call pays, so the call costs ₹4.76, the same as
the risk-neutral chance of an up move, 0.4762, times the ₹10 payoff. Many steps chain these into the
Cox-Ross-Rubinstein (CRR) tree. Two refinements are tested against it: averaging the n- and
(n + 1)-step prices, and Leisen-Reimer, which places the tree's nodes around the strike. The target
is Black-Scholes; on real data, every traded out-of-the-money NIFTY option on the last trading day
of each month, January 2015 to November 2026 (37,652 options, 7–365 days), priced on its forward
with that day's fitted volatility at its strike (from implied-vol-surface's local data), so Black-76
is the exact answer. Accuracy is counted against NSE's price step, one tick of ₹0.05.

- **Leisen-Reimer was exact in tens of steps.** It priced 98.2% of the real options within a tick
  at 25 steps and all of them at 51 (largest error ₹0.03); at 101 steps its median error was
  ₹0.0008.
- **The basic tree needed thousands.** CRR priced 17.2% within a tick at 100 steps, 60.6% at 500
  and 95.9% at 2,000. Its error halved each time the steps doubled; Leisen-Reimer's fell by about a
  quarter.
- **Averaging fixed the at-the-money zig-zag, not the rest.** At the money CRR's error flips sign
  between odd and even steps (−1.07 at 100 steps for a 30-day call worth ₹427), and the average
  cut it to −0.004. For a 10% out-of-the-money put it barely helped (−0.18 to −0.15): there the
  error follows where the strike falls between nodes. Across the real options at 100 steps the
  average halved the median error within 2% of the forward (₹0.37 to ₹0.19) and did nothing
  beyond 10% (₹0.10 to ₹0.11); it needed 1,000 steps for 96.4% within a tick.

## Quick start

```bash
uv sync
uv run btree report <topic>             # a study's numbers and charts -> out/
                                        # (topics: convergence)
uv run python scripts/build_site.py     # tree lab -> site/index.html (code only, no data)
uv run pytest
```

The lab and the tests need no market data; the tests of the browser maths need Node. Studies on
real NIFTY options read implied-vol-surface's local data (its daily SVI table and NSE option rows;
set `BTREE_IV_DIR` if that repo is not at `~/quant-learn/implied-vol-surface`); nothing from NSE is
committed here.

## Design

- `src/btree/tree.py`: the core maths in numpy (scipy only for the normal CDF): Black-Scholes with
  a continuous dividend yield as the closed-form reference; the Cox-Ross-Rubinstein tree
  (u = e^{σ√Δt}, d = 1/u, p = (e^{(r−q)Δt} − d)/(u − d), checked to lie in (0, 1)) with backward
  induction vectorised per step and American exercise at every node; `crr_tree` with the stock
  price, option value and early-exercise flag at every node (n ≤ 50); delta, gamma and theta from
  the step-1 and step-2 nodes; prices over a range of n, the n and n + 1 average, and
  Leisen-Reimer (Peizer-Pratt method 2, odd n).
- `src/btree/tree.js`: the lab's browser copy of the tree, Black-Scholes (with a double-precision
  normal CDF) and Leisen-Reimer, tested against Python through Node to 1e-9.
- `src/btree/batch.py`: European tree prices for many options at once as the discounted binomial
  average of payoffs (equal to backward induction, tested), for CRR and Leisen-Reimer.
- `src/btree/data.py`: month-end NIFTY option cases from implied-vol-surface's local data.
- `src/btree/reports.py`: README findings, reproducible with `btree report <topic>`.
- `src/btree/site.py`: the tree lab, one static Plotly page built from code alone.
- `src/btree/plots.py`: the shared chart style and the animated README charts.
- Conventions: time to expiry is calendar days / 365; rates and dividend yields are continuously
  compounded, a year; prices in rupees; node j at step i has j up moves.
- Charts: one validated palette; README charts are animated GIFs with a static fallback for
  reduced-motion users.

Research only, not investment advice. MIT licence.
