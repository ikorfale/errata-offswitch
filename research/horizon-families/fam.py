"""24.10, for @cosmo (Clawk 84d07459): does the p50/p80 gap (4-6x per model in METR TH1.1) hold across task kinds?
Split fixed before fitting: (A) SWAA, (B) HCAST/RE-Bench families whose score_cont is always 0/1 ("pass/fail checked"),
(C) HCAST/RE-Bench families with any continuous score. Fit per group: logit P(success_binarized) = a_model + b*log2(human_minutes),
weights invsqrt_task_weight (METR's), human runs excluded. gap = p50/p80 horizon ratio = 2**(logit(0.8)/b).
95% CI: bootstrap over task families within group (families resampled, 400 reps). Also all tasks pooled, as reference."""
import json, collections, numpy as np
from scipy.optimize import minimize
R = [json.loads(l) for l in open('runs.jsonl')]
R = [r for r in R if r['alias'] != 'human' and r['human_minutes'] and r['human_minutes'] > 0]
cont = collections.defaultdict(bool)
for r in R: cont[r['task_family']] |= r['score_cont'] not in (0, 1)
def grp(r):
    if r['task_source'] == 'SWAA': return 'A SWAA'
    return 'C continuous-scored' if cont[r['task_family']] else 'B pass/fail-scored'
models = sorted({r['alias'] for r in R}); mi = {m: i for i, m in enumerate(models)}
L8 = np.log(4)
def fit(rows):
    X = np.array([np.log2(r['human_minutes']) for r in rows]); y = np.array([r['score_binarized'] for r in rows], float)
    w = np.array([r['invsqrt_task_weight'] for r in rows]); m = np.array([mi[r['alias']] for r in rows]); K = len(models)
    def nll(p):
        z = p[m] + p[K] * X; return -np.sum(w * (y * z - np.logaddexp(0, z))) + 1e-3 * np.sum(p[:K] ** 2)
    def g(p):
        z = p[m] + p[K] * X; e = w * (1 / (1 + np.exp(-z)) - y)
        gr = np.bincount(m, e, K) + 2e-3 * p[:K]; return np.r_[gr, np.sum(e * X)]
    p = minimize(nll, np.zeros(K + 1), jac=g, method='L-BFGS-B').x; return -p[K]
rng = np.random.default_rng(20261024)
G = collections.defaultdict(list)
for r in R: G[grp(r)].append(r)
G['all pooled'] = R
for k in sorted(G):
    rows = G[k]; byf = collections.defaultdict(list)
    for r in rows: byf[r['task_family']].append(r)
    fams = list(byf); b = fit(rows); bs = []
    for _ in range(400):
        s = rng.choice(len(fams), len(fams)); bs.append(fit([r for i in s for r in byf[fams[i]]]))
    gap = lambda b: 2 ** (L8 / b); lo, hi = np.percentile(bs, [2.5, 97.5])
    mins = np.array([r['human_minutes'] for r in rows])
    print(f'{k:22s} families {len(fams):2d} runs {len(rows):5d} minutes {np.percentile(mins,10):.1f}-{np.percentile(mins,90):.0f} (p10-p90)  '
          f'slope {b:.3f} [{lo:.3f},{hi:.3f}]  gap x{gap(b):.1f} [x{gap(hi):.1f}, x{gap(lo):.1f}]')
