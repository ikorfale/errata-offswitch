"""Doubling time of METR's 50% and 80% time horizons (TH1.1 file, sha256 in README), SOTA models from 2023 on.
OLS of log2(horizon minutes) on release date; bootstrap over models (2000 resamples, seed 1) for intervals.
Same exclusion as METR's headline: drop points with central p50 > 16 h."""
import yaml, numpy as np, datetime as dt
d = yaml.safe_load(open('th11.yaml'))['results']
rows = []
for k, v in d.items():
    m = v['metrics']
    if not m.get('is_sota'): continue
    r = v['release_date']; r = r if isinstance(r, dt.date) else dt.date.fromisoformat(str(r))
    if r < dt.date(2023, 1, 1): continue
    p50, p80 = m['p50_horizon_length']['estimate'], m['p80_horizon_length']['estimate']
    if p50 > 16 * 60: continue
    rows.append((r, k, p50, p80))
rows.sort()
for r, k, a, b in rows: print(f'{r} {k:40s} p50={a:8.1f} p80={b:7.1f} ratio={a/b:5.1f}')
t = np.array([(r - dt.date(2023, 1, 1)).days for r, *_ in rows], float)
y50 = np.log2([a for _, _, a, _ in rows]); y80 = np.log2([b for *_, b in rows])
def dbl(t, y): return 1 / np.polyfit(t, y, 1)[0]
rng = np.random.default_rng(1); n = len(t); B = []
for _ in range(2000):
    i = rng.integers(0, n, n)
    if len(set(t[i])) < 3: continue
    B.append((dbl(t[i], y50[i]), dbl(t[i], y80[i]), dbl(t[i], y50[i]) - dbl(t[i], y80[i])))
B = np.array(B)
print(f'n={n} SOTA models 2023+')
print(f'doubling p50 {dbl(t,y50):.0f} d  [{np.percentile(B[:,0],2.5):.0f}, {np.percentile(B[:,0],97.5):.0f}]')
print(f'doubling p80 {dbl(t,y80):.0f} d  [{np.percentile(B[:,1],2.5):.0f}, {np.percentile(B[:,1],97.5):.0f}]')
print(f'p50 minus p80 doubling {dbl(t,y50)-dbl(t,y80):.0f} d  [{np.percentile(B[:,2],2.5):.0f}, {np.percentile(B[:,2],97.5):.0f}]')
ratio = y50 - y80
s = np.polyfit(t, ratio, 1)[0] * 365
print(f'log2(p50/p80) trend {s:+.2f} per year (positive = gap widening); first {2**ratio[0]:.1f}x last {2**ratio[-1]:.1f}x')
