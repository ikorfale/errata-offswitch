"""Checks suggested by Fable (22.10): (a) the 16 h exclusion applied per series (p50 rows cut on p50, p80 rows on p80);
(b) all 2023+ models, no is_sota filter; (c) p80-frontier selection (running record on p80). OLS log2 vs date, bootstrap 2000, seed 1."""
import yaml, numpy as np, datetime as dt
d = yaml.safe_load(open('th11.yaml'))['results']
def date(v):
    r = v['release_date']; return r if isinstance(r, dt.date) else dt.date.fromisoformat(str(r))
M = [(date(v), k, v['metrics']['p50_horizon_length']['estimate'], v['metrics']['p80_horizon_length']['estimate'], bool(v['metrics'].get('is_sota'))) for k, v in d.items()]
M = sorted(m for m in M if m[0] >= dt.date(2023, 1, 1))
def fit(pts, label):
    t = np.array([(r - dt.date(2023, 1, 1)).days for r, _ in pts], float); y = np.log2([h for _, h in pts])
    s = 1 / np.polyfit(t, y, 1)[0]; rng = np.random.default_rng(1); B = []
    for _ in range(2000):
        i = rng.integers(0, len(t), len(t))
        if len(set(t[i])) >= 3: B.append(1 / np.polyfit(t[i], y[i], 1)[0])
    print(f'{label:46s} n={len(t):2d} doubling {s:4.0f} d [{np.percentile(B,2.5):.0f}, {np.percentile(B,97.5):.0f}]')
sota = [m for m in M if m[4]]
fit([(r, a) for r, k, a, b, s in sota if a <= 960], '(a) p50, SOTA, cut p50>16h')
fit([(r, b) for r, k, a, b, s in sota if b <= 960], '(a) p80, SOTA, cut p80>16h (keeps mythos)')
fit([(r, a) for r, k, a, b, s in M if a <= 960], '(b) p50, all models, cut p50>16h')
fit([(r, b) for r, k, a, b, s in M if b <= 960], '(b) p80, all models, cut p80>16h')
rec, F = 0, []
for r, k, a, b, s in M:
    if b > rec: rec = b; F.append((r, b, k))
fit([(r, b) for r, b, k in F], '(c) p80 running record')
print('p80 record holders:', ', '.join(f'{k} {b:.0f}m' for r, b, k in F[-4:]))
