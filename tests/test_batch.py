import numpy as np

from btree import batch
from btree.tree import bs_price, crr, leisen_reimer


def test_batch_matches_backward_induction_and_black_scholes():
    rng = np.random.default_rng(0)
    S = rng.uniform(80, 120, 6)
    K = rng.uniform(80, 120, 6)
    T = rng.uniform(0.05, 1, 6)
    v = rng.uniform(0.1, 0.5, 6)
    args = list(zip(S, K, T, v, strict=True))
    for kind in ("call", "put"):
        for n in (7, 50):
            got = batch.crr_european(S, K, T, 0.06, 0.02, v, n, kind)
            want = [crr(s, k, t, 0.06, 0.02, x, n, kind) for s, k, t, x in args]
            assert np.allclose(got, want, rtol=1e-10, atol=1e-10)
            got = batch.lr_european(S, K, T, 0.06, 0.02, v, n, kind)
            want = [leisen_reimer(s, k, t, 0.06, 0.02, x, n, kind) for s, k, t, x in args]
            assert np.allclose(got, want, rtol=1e-9, atol=1e-9)
        bs = batch.bs_european(S, K, T, 0.06, 0.02, v, kind)
        want = [bs_price(s, k, t, 0.06, 0.02, x, kind) for s, k, t, x in args]
        assert np.allclose(bs, want)
