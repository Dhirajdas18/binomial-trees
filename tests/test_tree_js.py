import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from btree import tree as t

JS = Path(__file__).resolve().parents[1] / "src" / "btree" / "tree.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

CASES = [
    (25000.0, 25000.0, 30 / 365, 0.065, 0.012, 0.15),  # the lab's default
    (100.0, 100.0, 1.0, 0.05, 0.02, 0.2),
    (60.0, 100.0, 1.0, 0.08, 0.0, 0.2),  # deep in-the-money put
    (25000.0, 23500.0, 7 / 365, 0.065, 0.0, 0.35),
]
STYLES = [("call", False), ("put", False), ("call", True), ("put", True)]


def _node(expr: str):
    # The script goes in on stdin: Linux caps a single command-line argument at 128 KB.
    script = f"const g = require({json.dumps(str(JS))});console.log(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-"], input=script, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_browser_normal_cdf_matches_scipy():
    x = np.linspace(-9, 9, 721).tolist()
    assert _node(f"{json.dumps(x)}.map(g.normCdf)") == pytest.approx(
        t.norm.cdf(x).tolist(), rel=1e-12, abs=1e-15
    )


@pytest.mark.parametrize("a", CASES)
def test_browser_prices_match_python(a):
    js = _node(
        f"(() => {{ const a = {json.dumps(a)}, st = {json.dumps(STYLES)}; return {{"
        "bs: ['call', 'put'].map((k) => g.bsPrice(...a, k)),"
        "crr: st.map(([k, am]) => [1, 6, 12, 200].map((n) => g.crrPrice(...a, n, k, am))),"
        "lr: st.map(([k, am]) => [1, 6, 101, 200].map((n) => g.leisenReimer(...a, n, k, am))),"
        "gk: st.map(([k, am]) => g.crrGreeks(...a, 50, k, am)) }; })()"
    )
    assert js["bs"] == pytest.approx([t.bs_price(*a, k) for k in ("call", "put")], rel=1e-9)
    for i, (k, am) in enumerate(STYLES):
        py = [t.crr(*a, n, k, am) for n in (1, 6, 12, 200)]
        assert js["crr"][i] == pytest.approx(py, rel=1e-9, abs=1e-9)
        py = [t.leisen_reimer(*a, n, k, am) for n in (1, 6, 101, 200)]
        assert js["lr"][i] == pytest.approx(py, rel=1e-9, abs=1e-9)
        gk = t.crr_greeks(*a, 50, k, am)
        assert [js["gk"][i][f] for f in gk] == pytest.approx(list(gk.values()), rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("a", CASES)
@pytest.mark.parametrize("n", [1, 6, 12])
def test_browser_tree_arrays_match_python(a, n):
    js = _node(f"g.crrTree(...{json.dumps(a)}, {n}, 'put', true)")
    py = t.crr_tree(*a, n, "put", True)
    for key in ("dt", "u", "d", "p"):
        assert js[key] == pytest.approx(py[key], rel=1e-12)
    for i in range(n + 1):
        assert js["stock"][i] == pytest.approx(py["stock"][i].tolist(), rel=1e-9)
        assert js["value"][i] == pytest.approx(py["value"][i].tolist(), rel=1e-9, abs=1e-9)
        assert js["exercise"][i] == py["exercise"][i].tolist()


def test_browser_rejects_probability_out_of_range():
    out = _node("(() => { try { g.crrPrice(100, 100, 10, 0.1, 0, 0.01, 1, 'call', false); "
                "return 'no error'; } catch (e) { return e.message; } })()")
    assert "outside (0, 1)" in out
