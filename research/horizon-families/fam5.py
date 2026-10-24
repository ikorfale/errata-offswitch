"""gavinagent (Clawk, 24.10): which family has the widest p50/p80 ratio; does one family carry the average?
Same within-cell FE logit as fam4.py (intercept per (model, family) cell), but a separate slope per FAMILY,
shared across models. Only informative cells (mixed outcomes, >=2 distinct lengths) identify a slope; families with
<3 informative cells are listed but not ranked. Then leave-one-family-out shared slope: how far one family moves it."""
import json, collections, numpy as np
from scipy.optimize import minimize
R = [json.loads(l) for l in open('runs.jsonl')]
R = [r for r in R if r['alias'] != 'human' and r['human_minutes'] and r['human_minutes'] > 0]
def fit(rows, group):
    cells = sorted({(r['alias'], r['task_family']) for r in rows}); ci = {c: i for i, c in enumerate(cells)}; C = len(cells)
    gs = sorted({group(r) for r in rows}); gi = {g: i for i, g in enumerate(gs)}; S = len(gs)
    X = np.array([np.log2(r['human_minutes']) for r in rows]); y = np.array([r['score_binarized'] for r in rows], float)
    c = np.array([ci[(r['alias'], r['task_family'])] for r in rows]); s = np.array([gi[group(r)] for r in rows])
    def obj(p):
        z = p[c] + p[C + s] * X; e = 1 / (1 + np.exp(-z)) - y
        return (-np.sum(y * z - np.logaddexp(0, z)) + 1e-4 * np.sum(p[:C] ** 2),
                np.r_[np.bincount(c, e, C) + 2e-4 * p[:C], np.bincount(s, e * X, S)])
    p = minimize(obj, np.r_[np.zeros(C), -0.5 * np.ones(S)], jac=True, method='L-BFGS-B', options={'maxiter': 20000}).x
    return dict(zip(gs, -p[C:]))
g = collections.defaultdict(list)
for r in R: g[(r['alias'], r['task_family'])].append(r)
inf = collections.Counter(); runs = collections.Counter(); spread = collections.defaultdict(set)
for (m, f), rs in g.items():
    if 0 < sum(r['score_binarized'] for r in rs) < len(rs) and len({r['human_minutes'] for r in rs}) >= 2:
        inf[f] += 1; runs[f] += len(rs); spread[f] |= {r['human_minutes'] for r in rs}
b = fit(R, lambda r: r['task_family'])
x = lambda bb: 2 ** (np.log(4) / bb) if bb > 0 else float('inf')
ranked = sorted([f for f in b if inf[f] >= 3], key=lambda f: -x(b[f]))
print(f'families {len(b)}, with >=3 informative cells {len(ranked)}')
for f in ranked:
    lo, hi = min(spread[f]), max(spread[f])
    print(f'  {f:34s} b {b[f]:7.3f}  p50/p80 x{x(b[f]):8.1f}  inf cells {inf[f]:3d}  runs {runs[f]:5d}  lengths {lo:.0f}-{hi:.0f} min')
print('not ranked (<3 informative cells):', sum(1 for f in b if inf[f] < 3))
base = fit(R, lambda r: 0)[0]; print(f'shared slope all families {base:.3f} x{x(base):.1f}')
top = ranked  # all ranked families (draft claimed "any one"; 24.10 first run covered only 6)
for f in top:
    bb = fit([r for r in R if r['task_family'] != f], lambda r: 0)[0]
    print(f'  drop {f:34s} shared x{x(bb):.2f}')
