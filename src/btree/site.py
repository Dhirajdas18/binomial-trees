"""The tree lab: one static Plotly page built from code alone (tree.js does the maths in the
browser), so the Pages build needs no data and no schedule."""

import datetime
import re
from pathlib import Path
from string import Template

from btree import plots

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
ICON = (
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22%3E"
    "%3Cpath d=%22M2 8l6-5M2 8l6 5M8 3l6-2M8 3l6 5M8 13l6-5M8 13l6 2%22 fill=%22none%22"
    " stroke=%22%232a78d6%22 stroke-width=%221.6%22 stroke-linecap=%22round%22/%3E"
    "%3C/svg%3E"
)
HERE = Path(__file__).parent
JS = (HERE / "tree.js").read_text(encoding="utf-8")
LAB = (HERE / "lab.html").read_text(encoding="utf-8")
PAGE = Template((HERE / "page.html").read_text(encoding="utf-8"))
REPO = "https://github.com/Dhirajdas18/binomial-trees"


def lab_section() -> str:
    return LAB.replace("$js", JS)


def method_section() -> str:
    return """<ul class="plain">
<li>The tree is Cox-Ross-Rubinstein’s. The time to expiry T (calendar days / 365) is cut into n
equal steps of Δt = T / n. Each step the share price is multiplied by u = e<sup>σ√Δt</sup> (up)
or d = 1 / u (down), so an up and a down move bring it back where it was. The up move gets the
risk-neutral probability p = (e<sup>(r − q)Δt</sup> − d) / (u − d), the one that makes the share
earn the interest rate r minus the dividend yield q on average. If p falls outside 0 to 1 (a long
step with a tiny volatility) the tree is not valid and the lab says so.</li>
<li>At expiry the option is worth its payoff. Each earlier node is worth
e<sup>−rΔt</sup>(p × value after an up move + (1 − p) × value after a down move). An American
option takes the larger of that and the value of exercising there and then; nodes where
exercising wins are marked.</li>
<li>Black-Scholes, with the same continuous dividend yield, is the closed-form reference. For an
American option it is the European price, shown for comparison only. The early-exercise premium
is the American tree price minus the European tree price, both with 200 steps.</li>
<li>Delta and gamma come from the tree’s first two steps (the change in option value between the
step-1 nodes, and the change in that across the step-2 nodes); theta from the middle step-2 node,
which sits at today’s share price two steps later. They use 200 steps.</li>
<li>The averaged tree is the mean of the n- and (n + 1)-step prices. Leisen-Reimer uses the
Peizer-Pratt inversion (method 2) to set p and the moves so the tree lines up with the strike; it
needs an odd number of steps.</li>
<li>A tree moves in discrete steps, so it only approximates a share price that moves all the
time; its error shrinks as the steps grow. One volatility, rate and dividend yield are assumed to
hold to expiry, and real dividends are paid in cash on set dates, not as a smooth yield.</li>
<li>NIFTY and NSE stock options are European, so the American choice is here for understanding
how early exercise works, not for pricing a listed contract.</li>
</ul>"""


SECTIONS = [
    (
        "Tree lab",
        "Change any input and both charts redraw. Research only, not investment advice.",
        lab_section,
    ),
    (
        "Method and caveats",
        "What the lab computes, and what it leaves out.",
        method_section,
    ),
]


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build_html() -> str:
    parts, nav = [], []
    for title, blurb, make in SECTIONS:
        sid = _slug(title)
        nav.append(f'<li><a href="#{sid}">{title}</a></li>')
        body = make()
        parts.append(f'<section id="{sid}">\n<h2>{title}</h2>\n<p>{blurb}</p>\n{body}\n</section>')
    dk = plots.DARK
    s = plots.SERIES
    return PAGE.substitute(
        updated=datetime.date.today().strftime("%d %b %Y").lstrip("0"),
        icon=ICON,
        font=FONT,
        repo=REPO,
        surface=plots.SURFACE,
        text=plots.TEXT,
        text2=plots.TEXT_2,
        grid=plots.GRID,
        accent=s[0],
        accent2=s[1],
        green=s[2],
        violet=s[6],
        muted=plots.MUTED,
        d_surface=dk[plots.SURFACE],
        d_text=dk[plots.TEXT],
        d_text2=dk[plots.TEXT_2],
        d_grid=dk[plots.GRID],
        d_accent=dk[s[0]],
        d_accent2=dk[s[1]],
        d_green=dk[s[2]],
        d_violet=dk[s[6]],
        d_muted="#6b6a64",
        nav="\n".join(nav),
        sections="\n".join(parts),
    )
