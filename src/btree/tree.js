// Tree maths in the browser. Mirrors src/btree/tree.py; tests compare the two through Node.
// Arguments as in Python: S spot, K strike, T years, r rate, q dividend yield, sigma vol a year,
// n steps, kind "call" or "put". Node j at step i has j up moves.

// Standard normal CDF to double precision (Hart 1968, as given by West 2005).
function normCdf(x) {
  const a = Math.abs(x);
  let c = 0;
  if (a <= 37) {
    const e = Math.exp(-a * a / 2);
    if (a < 7.07106781186547) {
      let num = 3.52624965998911e-2 * a + 0.700383064443688;
      num = num * a + 6.37396220353165;
      num = num * a + 33.912866078383;
      num = num * a + 112.079291497871;
      num = num * a + 221.213596169931;
      num = num * a + 220.206867912376;
      let den = 8.83883476483184e-2 * a + 1.75566716318264;
      den = den * a + 16.064177579207;
      den = den * a + 86.7807322029461;
      den = den * a + 296.564248779674;
      den = den * a + 637.333633378831;
      den = den * a + 793.826512519948;
      den = den * a + 440.413735824752;
      c = e * num / den;
    } else {
      c = e / (a + 1 / (a + 2 / (a + 3 / (a + 4 / (a + 0.65))))) / 2.506628274631;
    }
  }
  return x > 0 ? 1 - c : c;
}

function bsPrice(S, K, T, r, q, sigma, kind) {
  const vt = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt, d2 = d1 - vt;
  const s = kind === "call" ? 1 : -1;
  return s * (S * Math.exp(-q * T) * normCdf(s * d1) - K * Math.exp(-r * T) * normCdf(s * d2));
}

const payoff = (st, K, kind) => Math.max(kind === "call" ? st - K : K - st, 0);

function crrParams(T, r, q, sigma, n) {
  const dt = T / n, u = Math.exp(sigma * Math.sqrt(dt)), d = 1 / u;
  const p = (Math.exp((r - q) * dt) - d) / (u - d);
  if (!(p > 0 && p < 1)) {
    throw new Error(`risk-neutral probability p = ${p.toFixed(4)} is outside (0, 1); use more steps or a higher volatility`);
  }
  return { dt, u, d, p };
}

// Backward induction; keepAll returns every step's { stock, value, exercise }, else the price.
function induct(S, K, T, r, n, u, d, p, kind, american, keepAll) {
  const disc = Math.exp(-r * T / n), tol = 1e-9 * K;
  const node = (i, j) => S * u ** j * d ** (i - j);
  let value = Array.from({ length: n + 1 }, (_, j) => payoff(node(n, j), K, kind));
  const stock = [], values = [], exercise = [];
  if (keepAll) {
    stock[n] = value.map((_, j) => node(n, j)); values[n] = value; exercise[n] = value.map(() => false);
  }
  for (let i = n - 1; i >= 0; i--) {
    const next = new Array(i + 1), ex = new Array(i + 1).fill(false), st = new Array(i + 1);
    for (let j = 0; j <= i; j++) {
      st[j] = node(i, j);
      next[j] = disc * (p * value[j + 1] + (1 - p) * value[j]);
      if (american) {
        const iv = payoff(st[j], K, kind);
        ex[j] = iv > next[j] + tol;
        next[j] = Math.max(next[j], iv);
      }
    }
    value = next;
    if (keepAll) { stock[i] = st; values[i] = next; exercise[i] = ex; }
  }
  return keepAll ? { stock, value: values, exercise } : value[0];
}

function crrPrice(S, K, T, r, q, sigma, n, kind, american) {
  const { u, d, p } = crrParams(T, r, q, sigma, n);
  return induct(S, K, T, r, n, u, d, p, kind, american, false);
}

function crrTree(S, K, T, r, q, sigma, n, kind, american) {
  const prm = crrParams(T, r, q, sigma, n);
  return Object.assign(prm, induct(S, K, T, r, n, prm.u, prm.d, prm.p, kind, american, true));
}

// Delta and gamma from the step-1 and step-2 nodes, theta (a year) from the step-2 middle node.
function crrGreeks(S, K, T, r, q, sigma, n, kind, american) {
  const g = crrTree(S, K, T, r, q, sigma, n, kind, american);
  const [s1, s2, f1, f2] = [g.stock[1], g.stock[2], g.value[1], g.value[2]];
  const dUp = (f2[2] - f2[1]) / (s2[2] - s2[1]), dDn = (f2[1] - f2[0]) / (s2[1] - s2[0]);
  return { price: g.value[0][0], delta: (f1[1] - f1[0]) / (s1[1] - s1[0]),
    gamma: (dUp - dDn) / (0.5 * (s2[2] - s2[0])), theta: (f2[1] - g.value[0][0]) / (2 * g.dt) };
}

// Peizer-Pratt inversion, method 2.
function pp2(z, n) {
  const x = z / (n + 1 / 3 + 0.1 / (n + 1));
  return 0.5 + Math.sign(z) * Math.sqrt(0.25 - 0.25 * Math.exp(-x * x * (n + 1 / 6)));
}

// Leisen-Reimer; an even n uses n + 1.
function leisenReimer(S, K, T, r, q, sigma, n, kind, american) {
  if (n % 2 === 0) n += 1;
  const vt = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt, d2 = d1 - vt;
  const p = pp2(d2, n), g = Math.exp((r - q) * T / n), u = g * pp2(d1, n) / p;
  const d = (g - p * u) / (1 - p);
  return induct(S, K, T, r, n, u, d, p, kind, american, false);
}

if (typeof module !== "undefined") {
  module.exports = { normCdf, bsPrice, crrParams, crrPrice, crrTree, crrGreeks, leisenReimer };
}
