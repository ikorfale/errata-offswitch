"""Fable review 24.10 of fam3.py: shared family intercepts leak model x family interaction into slopes. Fix: a separate
intercept for every (model, family) cell, so only within-cell length variation identifies the slope (FE logit; cells
at floor/ceiling carry no information). Shared slope, all tasks / no SWAA / without Opus 4.6 / pre-2025.5 models;
then per-model slopes with counts of informative cells (mixed outcomes and >=2 distinct lengths). Unweighted and
METR-weighted."""
import json, collections, numpy as np, sys
from scipy.optimize import minimize
R = [json.loads(l) for l in open('runs.jsonl')]
R = [r for r in R if r['alias'] != 'human' and r['human_minutes'] and r['human_minutes'] > 0]
def fit(rows, weighted, per_model=False):
    cells = sorted({(r['alias'], r['task_family']) for r in rows}); ci = {c: i for i, c in enumerate(cells)}; C = len(cells)
    ms = sorted({r['alias'] for r in rows}); mi = {m: i for i, m in enumerate(ms)}; S = len(ms) if per_model else 1
    X = np.array([np.log2(r['human_minutes']) for r in rows]); y = np.array([r['score_binarized'] for r in rows], float)
    w = np.array([r['invsqrt_task_weight'] if weighted else 1.0 for r in rows]); w = w / w.mean()
    c = np.array([ci[(r['alias'], r['task_family'])] for r in rows]); s = np.array([mi[r['alias']] for r in rows]) if per_model else np.zeros(len(rows), int)
    def obj(p):
        z = p[c] + p[C + s] * X; e = w * (1 / (1 + np.exp(-z)) - y)
        return (-np.sum(w * (y * z - np.logaddexp(0, z))) + 1e-4 * np.sum(p[:C] ** 2),
                np.r_[np.bincount(c, e, C) + 2e-4 * p[:C], np.bincount(s, e * X, S)])
    p = minimize(obj, np.r_[np.zeros(C), -0.5 * np.ones(S)], jac=True, method='L-BFGS-B', options={'maxiter': 20000}).x
    return -p[C:], ms
def informative(rows):
    g = collections.defaultdict(list)
    for r in rows: g[(r['alias'], r['task_family'])].append(r)
    n = collections.Counter()
    for (m, f), rs in g.items():
        if 0 < sum(r['score_binarized'] for r in rs) < len(rs) and len({r['human_minutes'] for r in rs}) >= 2: n[m] += 1
    return n
early = {'GPT-4 0314', 'GPT-4 1106 (Inspect)', 'Claude 3 Opus (Inspect)', 'GPT-4 Turbo (Inspect)', 'GPT-4o (Inspect)',
         'Claude 3.5 Sonnet (Old) (Inspect)', 'o1-preview', 'Claude 3.5 Sonnet (New) (Inspect)', 'o1 (Inspect)', 'Claude 3.7 Sonnet (Inspect)', 'o3 (Inspect)'}
subsets = [('all tasks', R), ('no SWAA', [r for r in R if r['task_source'] != 'SWAA']),
           ('all, without Opus 4.6', [r for r in R if r['alias'] != 'Claude Opus 4.6 (Inspect)']),
           ('11 models up to o3 (Apr 2025)', [r for r in R if r['alias'] in early])]
for wt in (False, True):
    for name, rows in subsets:
        b, _ = fit(rows, wt); print(f'{"weighted" if wt else "unweighted":10s} {name:32s} shared within-cell slope {b[0]:.3f}  p50/p80 x{2 ** (np.log(4) / b[0]):.1f}', flush=True)
b, ms = fit(R, False, per_model=True); n = informative(R)
for m, bb in zip(ms, b): print(f'  per-model unweighted {m:36s} b {bb:.3f}  x{2 ** (np.log(4) / bb) if bb > 0 else float("nan"):6.1f}  informative cells {n[m]}')
