"""Fable review 22.10 of tost.py: model bootstrap undercovers. Gap slope log2(p50/p80)/yr with classical t and HC3 90% intervals;
ceiling rule fixed by a stated criterion (drop models whose p50 ci_high > 16 h) instead of dropping one model by name.
log2(p50/p80) = logit(0.8)/beta of each model's own logistic fit, so this is a test of whether success curves get steeper."""
import yaml, numpy as np, datetime as dt
from scipy import stats
d = yaml.safe_load(open('th11.yaml'))['results']
def date(v):
    r = v['release_date']; return r if isinstance(r, dt.date) else dt.date.fromisoformat(str(r))
M = sorted((date(v), k, v['metrics']['p50_horizon_length'], v['metrics']['p80_horizon_length']['estimate'],
            bool(v['metrics'].get('is_sota'))) for k, v in d.items())
M = [m for m in M if m[0] >= dt.date(2023, 1, 1)]
def run(rows, label):
    t = np.array([(r - dt.date(2023, 1, 1)).days / 365.25 for r, *_ in rows]); g = np.log2([a['estimate'] / b for _, _, a, b, _ in rows])
    X = np.c_[np.ones_like(t), t]; n = len(t); XtXi = np.linalg.inv(X.T @ X); b = XtXi @ X.T @ g; e = g - X @ b
    se = np.sqrt(e @ e / (n - 2) * XtXi[1, 1]); h = np.einsum('ij,jk,ik->i', X, XtXi, X)
    se3 = np.sqrt((XtXi @ X.T @ np.diag(e**2 / (1 - h)**2) @ X @ XtXi)[1, 1]); q = stats.t.ppf(0.95, n - 2)
    print(f'{label:44s} n={n:2d} slope {b[1]:+.2f}/yr  90% t [{b[1]-q*se:+.2f}, {b[1]+q*se:+.2f}]  HC3 [{b[1]-q*se3:+.2f}, {b[1]+q*se3:+.2f}]'
          f'  -> 3-yr ratio x{2**(3*(b[1]-q*se3)):.2f}..x{2**(3*(b[1]+q*se3)):.2f}')
S = [m for m in M if m[4]]
run([m for m in S if m[2]['estimate'] <= 960], 'SOTA, p50 estimate <=16h (as posted)')
run([m for m in S if m[2]['ci_high'] <= 960], 'SOTA, p50 ci_high <=16h (ceiling rule)')
run([m for m in M if m[2]['estimate'] <= 960], 'all 2023+, p50 estimate <=16h')
run([m for m in M if m[2]['ci_high'] <= 960], 'all 2023+, p50 ci_high <=16h')
print('dropped by ceiling rule:', [m[1] for m in S if m[2]['ci_high'] > 960])
