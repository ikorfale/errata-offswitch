"""Fable review 24.10 of fam.py: SWAA vs the rest drives the pooled slope; check slopes only (2000 family-cluster reps):
B+C pooled without SWAA; B+C with a B/C intercept dummy; B+C baseline-timed tasks only; B+C with family fixed effects."""
import json, collections, numpy as np
from scipy.optimize import minimize
R = [json.loads(l) for l in open('runs.jsonl')]
R = [r for r in R if r['alias'] != 'human' and r['human_minutes'] and r['human_minutes'] > 0 and r['task_source'] != 'SWAA']
cont = collections.defaultdict(bool)
for r in R: cont[r['task_family']] |= r['score_cont'] not in (0, 1)
models = sorted({r['alias'] for r in R})
def fit(rows, extra):
    """extra(r) -> category for additional intercepts (None = none)."""
    cats = sorted({extra(r) for r in rows}, key=str); ci = {c: i for i, c in enumerate(cats)}
    mi = {m: i for i, m in enumerate(models)}; K = len(models); C = len(cats)
    X = np.array([np.log2(r['human_minutes']) for r in rows]); y = np.array([r['score_binarized'] for r in rows], float)
    w = np.array([r['invsqrt_task_weight'] for r in rows]); m = np.array([mi[r['alias']] for r in rows]); c = np.array([ci[extra(r)] for r in rows])
    def f(p):
        z = p[m] + p[K + c] + p[-1] * X; e = w * (1 / (1 + np.exp(-z)) - y)
        v = -np.sum(w * (y * z - np.logaddexp(0, z))) + 1e-3 * np.sum(p[:-1] ** 2)
        return v, np.r_[np.bincount(m, e, K) + 2e-3 * p[:K], np.bincount(c, e, C) + 2e-3 * p[K:K + C], np.sum(e * X)]
    return -minimize(f, np.zeros(K + C + 1), jac=True, method='L-BFGS-B').x[-1]
rng = np.random.default_rng(20261024)
variants = [('B+C pooled, no SWAA', R, lambda r: None),
            ('B+C, B/C intercept dummy', R, lambda r: cont[r['task_family']]),
            ('B+C, baseline-timed only', [r for r in R if r['human_source'] == 'baseline'], lambda r: None),
            ('B+C, family fixed effects', R, lambda r: r['task_family'])]
import sys
only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
for vi, (name, rows, ex) in enumerate(variants):
    if only and str(vi) not in only: continue
    byf = collections.defaultdict(list)
    for r in rows: byf[r['task_family']].append(r)
    fams = list(byf); b = fit(rows, ex); bs = []
    for _ in range(int(__import__('sys').argv[1]) if len(__import__('sys').argv) > 1 else 2000):
        s = rng.choice(len(fams), len(fams)); sub = []
        for j, i in enumerate(s): sub += [dict(r, task_family=f'{r["task_family"]}#{j}') for r in byf[fams[i]]] if name.endswith('effects') else byf[fams[i]]
        bs.append(fit(sub, ex))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    print(f'{name:28s} families {len(fams):2d} runs {len(rows):5d} slope {b:.3f} [{lo:.3f}, {hi:.3f}]  (p50/p80 x{2**(np.log(4)/b):.1f})', flush=True)
