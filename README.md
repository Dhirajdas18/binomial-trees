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

- [ ] One step to many: replication, risk-neutral probability, CRR and its convergence to Black-Scholes
- [ ] Greeks from the tree
- [ ] American options: the early-exercise premium and boundary
- [ ] Discrete cash dividends on NSE stocks
- [ ] Trinomial trees and barrier options
- [ ] An implied tree fitted to the NIFTY smile
- [ ] Does a smile-fitted tree hedge better than Black-Scholes

## Findings

Findings are added as each study is completed.

## Quick start

```bash
uv sync
uv run btree report <topic>             # a study's numbers and charts -> out/
                                        # (topics are added as each study is completed)
uv run python scripts/build_site.py     # tree lab -> site/index.html (code only, no data)
uv run pytest
```

The lab and the tests need no market data; the tests of the browser maths need Node.

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
- `src/btree/reports.py`: README findings, reproducible with `btree report <topic>`.
- `src/btree/site.py`: the tree lab, one static Plotly page built from code alone.
- `src/btree/plots.py`: the shared chart style and the animated README charts.
- Conventions: time to expiry is calendar days / 365; rates and dividend yields are continuously
  compounded, a year; prices in rupees; node j at step i has j up moves.
- Charts: one validated palette; README charts are animated GIFs with a static fallback for
  reduced-motion users.

Research only, not investment advice. MIT licence.
