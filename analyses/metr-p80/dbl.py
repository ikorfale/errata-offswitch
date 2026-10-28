"""Doubling time of METR TH1.1 p50 vs p80 horizons (SOTA models, release >= 2023, p50 <= 16 h as METR's own fit),
and the trend of the p50/p80 ratio. Bootstrap over models, 4000 resamples, seed 1. Input th11.yaml (sha256 in out)."""
import yaml, numpy as np, datetime as dt, hashlib
raw = open("th11.yaml", "rb").read(); d = yaml.safe_load(raw)
rows = []
for k, v in d["results"].items():
    m = v["metrics"]; r = v["release_date"]; r = r if isinstance(r, dt.date) else dt.date.fromisoformat(str(r))
    if not m.get("is_sota") or r < dt.date(2023, 1, 1): continue
    p50, p80 = m["p50_horizon_length"]["estimate"], m["p80_horizon_length"]["estimate"]
    if p50 > 16 * 60: continue
    rows.append((r.toordinal(), np.log2(p50), np.log2(p80), k, r, p50, p80))
rows.sort()
print("sha256", hashlib.sha256(raw).hexdigest()[:16], "models", len(rows))
for x in rows: print(f"  {x[4]} {x[3][:38]:38} p50 {x[5]:8.1f} min  p80 {x[6]:7.1f} min  ratio {x[5]/x[6]:5.1f}")
t = np.array([x[0] for x in rows], float); a = np.array([x[1] for x in rows]); b = np.array([x[2] for x in rows])
def fit(t, y): return np.polyfit(t, y, 1)[0]
s50, s80, sr = fit(t, a), fit(t, b), fit(t, a - b)
print(f"doubling p50 {1/s50:.1f} d  p80 {1/s80:.1f} d  log2(p50/p80) slope per year {sr*365:.3f}")
rng = np.random.default_rng(1); B = []
for _ in range(4000):
    i = rng.integers(0, len(t), len(t))
    if len(set(t[i])) < 3: continue
    B.append((1 / fit(t[i], a[i]), 1 / fit(t[i], b[i]), fit(t[i], a[i] - b[i]) * 365))
B = np.array(B); q = lambda c: np.percentile(B[:, c], [2.5, 97.5]).round(2)
print("95% boot: p50", q(0), " p80", q(1), " ratio slope/yr", q(2), " share of resamples with p80 faster:", round(float(np.mean(B[:, 1] < B[:, 0])), 3))
print("excluded SOTA >= 2023 with p50 > 16 h:", [(k, str(v["release_date"]), round(v["metrics"]["p50_horizon_length"]["estimate"]), round(v["metrics"]["p80_horizon_length"]["estimate"])) for k, v in d["results"].items() if v["metrics"].get("is_sota") and v["metrics"]["p50_horizon_length"]["estimate"] > 960])
t2, a2, b2 = t[:-1], a[:-1], b[:-1]
print(f"without the last model: doubling p50 {1/fit(t2,a2):.1f} d  p80 {1/fit(t2,b2):.1f} d  ratio slope/yr {fit(t2,a2-b2)*365:.3f}")
