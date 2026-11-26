import numpy as np

from btree import batch
from btree.tree import crr, leisen_reimer


def test_batch_american_matches_backward_induction():
    S, K, T, v = [100.0, 90.0], [100.0, 100.0], [0.5, 1.0], [0.2, 0.3]
    for kind in ("put", "call"):
        for method, fn in (("crr", crr), ("lr", leisen_reimer)):
            got = batch.american(S, K, T, 0.08, 0.03, v, 101, kind, method)
            want = [fn(s, k, t, 0.08, 0.03, x, 101, kind, american=True)
                    for s, k, t, x in zip(S, K, T, v, strict=True)]
            assert np.allclose(got, want, rtol=1e-10)


def test_american_call_without_dividends_is_european():
    a = ([100.0], [95.0], [1.0], 0.06, 0.0, [0.25])
    am = batch.american(*a, 201, "call", "lr")[0]
    assert np.isclose(am, batch.lr_european(*a, 201, "call")[0])


def test_put_boundary_sits_below_the_strike_and_rises_towards_expiry():
    t, e = batch.exercise_boundary(100.0, 100.0, 1.0, 0.065, 0.013, 0.2, 1000)
    ok = np.isfinite(e)
    assert (e[ok] < 100).all()
    first, last = e[ok][:50].mean(), e[ok][-50:].mean()
    assert first < last
