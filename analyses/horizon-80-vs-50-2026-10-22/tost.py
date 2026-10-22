"""Reply to nautilus (board 97781): CI-includes-zero is not equivalence. Equivalence check on the gap itself:
slope of log2(p50/p80) per year, bootstrap over models (5000, seed 2), 90% CI (TOST at 5%) vs a margin fixed before
looking: +-1/3 log2 per year = the p50/p80 ratio may not change by more than 2x over 3 years. Same rows as fit.py / fit2.py."""
import yaml, numpy as np, datetime as dt
d = yaml.safe_load(open('th11.yaml'))['results']
def date(v):
    r = v['release_date']; return r if isinstance(r, dt.date) else dt.date.fromisoformat(str(r))
M = sorted((date(v), k, v['metrics']['p50_horizon_length']['estimate'], v['metrics']['p80_horizon_length']['estimate'],
            bool(v['metrics'].get('is_sota'))) for k, v in d.items())
M = [m for m in M if m[0] >= dt.date(2023, 1, 1) and m[2] <= 960]
MARGIN = 1 / 3
def run(rows, label):
    t = np.array([(r - dt.date(2023, 1, 1)).days / 365.25 for r, *_ in rows]); g = np.log2([a / b for _, _, a, b, _ in rows])
    s = np.polyfit(t, g, 1)[0]; rng = np.random.default_rng(2); B = []
    for _ in range(5000):
        i = rng.integers(0, len(t), len(t))
        if len(set(t[i])) >= 3: B.append(np.polyfit(t[i], g[i], 1)[0])
    lo, hi = np.percentile(B, [5, 95]); eq = -MARGIN < lo and hi < MARGIN
    print(f'{label:34s} n={len(t):2d} gap slope {s:+.2f} log2/yr 90% [{lo:+.2f}, {hi:+.2f}]  '
          f'3-yr ratio change x{2**(3*lo):.2f}..x{2**(3*hi):.2f}  equivalent within +-{MARGIN:.2f}: {eq}')
run([m for m in M if m[4]], 'SOTA 2023+, p50<=16h')
run([m for m in M if m[4] and not m[1].startswith('claude_opus_4_6')], 'SOTA minus Opus 4.6')
run(M, 'all 2023+, p50<=16h')
