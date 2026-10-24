"""24.10 follow-up: does the WITHIN-family reliability gap shrink over model generations?
logit P = a_model + c_family + b_model * log2(human_minutes); all 79 families, METR weights; family intercepts shared.
Per model: within-family p50/p80 = 2^(ln4/b_model), next to METR's own per-model ratio (th11.yaml). Then trend of
log2(gap) on release date, models released 2023+. Bootstrap over families (argv[1] reps, default 0)."""
import json, sys, collections, datetime as dt, numpy as np, yaml
from scipy.optimize import minimize
R = [json.loads(l) for l in open('runs.jsonl')]
R = [r for r in R if r['alias'] != 'human' and r['human_minutes'] and r['human_minutes'] > 0]
Y = yaml.safe_load(open('th11.yaml'))['results']
key = lambda r: 'gpt_5_3_codex' if r['model'] == 'flamingo_2' else r['model']
models = sorted({key(r) for r in R}); mi = {m: i for i, m in enumerate(models)}; K = len(models)
def date(m):
    v = Y[m]['release_date']; return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))
def fit(rows):
    fams = sorted({r['task_family'] for r in rows}); fi = {f: i for i, f in enumerate(fams)}; F = len(fams)
    X = np.array([np.log2(r['human_minutes']) for r in rows]); y = np.array([r['score_binarized'] for r in rows], float)
    w = np.array([r['invsqrt_task_weight'] for r in rows]); m = np.array([mi[key(r)] for r in rows]); f = np.array([fi[r['task_family']] for r in rows])
    def obj(p):
        z = p[m] + p[K + f] + p[K + F + m] * X; e = w * (1 / (1 + np.exp(-z)) - y)
        v = -np.sum(w * (y * z - np.logaddexp(0, z))) + 1e-3 * np.sum(p[:K + F] ** 2)
        return v, np.r_[np.bincount(m, e, K) + 2e-3 * p[:K], np.bincount(f, e, F) + 2e-3 * p[K:K + F], np.bincount(m, e * X, K)]
    p0 = np.r_[np.zeros(K + F), -0.5 * np.ones(K)]
    return -minimize(obj, p0, jac=True, method='L-BFGS-B', options={'maxiter': 5000}).x[K + F:]
def trend(b):
    sel = [i for i, mm in enumerate(models) if date(mm) >= dt.date(2023, 1, 1) and b[i] > 0.05]
    t = np.array([(date(models[i]) - dt.date(2023, 1, 1)).days / 365.25 for i in sel]); g = np.log2(2 ** (np.log(4) / b[sel]))
    return np.polyfit(t, g, 1)[0], len(sel)
b = fit(R)
print(f'{"model":38s} {"release":10s} {"b_within":>8s} {"gap_within":>10s} {"gap_METR":>8s}')
for i in sorted(range(K), key=lambda i: date(models[i])):
    mm = models[i]; met = Y[mm]['metrics']; gm = met['p50_horizon_length']['estimate'] / met['p80_horizon_length']['estimate']
    print(f'{mm:38s} {date(mm)!s:10s} {b[i]:8.3f} {2 ** (np.log(4) / b[i]) if b[i] > 0 else float("nan"):10.1f} {gm:8.1f}')
s, n = trend(b); print(f'trend of log2(within gap) on date, {n} models 2023+: {s:+.2f} log2/yr (x{2 ** s:.2f} per year)')
reps = int(sys.argv[1]) if len(sys.argv) > 1 else 0
if reps:
    rng = np.random.default_rng(20261024); byf = collections.defaultdict(list)
    for r in R: byf[r['task_family']].append(r)
    fams = list(byf); ss = []
    for _ in range(reps):
        sub = [dict(r, task_family=f'{fams[i]}#{j}') for j, i in enumerate(rng.choice(len(fams), len(fams))) for r in byf[fams[i]]]
        ss.append(trend(fit(sub))[0])
    print(f'bootstrap over families ({reps}): trend 95% [{np.percentile(ss, 2.5):+.2f}, {np.percentile(ss, 97.5):+.2f}] log2/yr')
