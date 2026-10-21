#!/usr/bin/env python3
"""Build offswitch.errata.page (static) from data/: state.json, history.jsonl, events.jsonl, signals/latest.json,
reports/*.md and METHOD.md. Output in site/. Stdlib only, plus matplotlib for the share card."""
import json, os, re, html, glob, shutil, datetime as dt

ROOT = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site')
BASE = 'https://offswitch.errata.page'
LEVELS = [(0, 'Contained'), (20, 'Supervised'), (40, 'Slipping'), (60, 'Loose'), (80, 'Off-switch failed')]
COMP = [('capability', 'Capability', 30), ('misbehaviour', 'Misbehaviour', 25), ('exposure', 'Exposure', 15),
        ('oversight', 'Oversight gap', 20), ('race', 'Race', 10)]
FAM = {'research': 'Research', 'incidents': 'Incidents', 'cyber': 'Cyber', 'exposure': 'Exposure', 'attention': 'Attention'}
e = lambda s: html.escape(str(s if s is not None else ''), quote=True)


def jl(p):
    if not os.path.exists(p): return []
    return [json.loads(l) for l in open(p) if l.strip()]


def level(v):
    name = LEVELS[0][1]
    for lo, n in LEVELS:
        if v >= lo: name = n
    return name


def inline(s):
    s = e(s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)', r'<a href="\2">\1</a>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<![\w*])\*([^*\n]+)\*(?!\w)', r'<i>\1</i>', s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    return s


def md(text):
    """Small Markdown subset: #, paragraphs, - lists, 1. lists, | tables |, **b**, *i*, `c`, [a](u)."""
    out, lines, i = [], text.split('\n'), 0
    while i < len(lines):
        l = lines[i]
        if not l.strip(): i += 1; continue
        m = re.match(r'(#{1,4}) (.*)', l)
        if m:
            n = len(m.group(1)); t = m.group(2)
            sid = re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')
            out.append(f'<h{n} id="{sid}">{inline(t)}</h{n}>'); i += 1; continue
        if l.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells): rows.append(cells)
                i += 1
            h = ''.join(f'<th>{inline(c)}</th>' for c in rows[0])
            b = ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>' for r in rows[1:])
            out.append(f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'); continue
        if re.match(r'\s*([-*]|\d+\.) ', l):
            tag = 'ol' if re.match(r'\s*\d+\.', l) else 'ul'; items = []
            while i < len(lines) and lines[i].strip():
                if re.match(r'\s*([-*]|\d+\.) ', lines[i]): items.append(re.sub(r'\s*([-*]|\d+\.) ', '', lines[i], count=1))
                else: items[-1] += ' ' + lines[i].strip()
                i += 1
            out.append(f'<{tag}>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + f'</{tag}>'); continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r'(#{1,4} |\||\s*([-*]|\d+\.) )', lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append(f'<p>{inline(" ".join(para))}</p>')
    return '\n'.join(out)


def spark(series, hot):
    vals = [v or 0 for _, v in series][-90:]
    if len(vals) < 2: return ''
    w, h = 120, 28; mx = max(vals) or 1
    pts = ' '.join(f'{i * w / (len(vals) - 1):.1f},{h - 2 - v / mx * (h - 4):.1f}' for i, v in enumerate(vals))
    return f'<svg class="spark{" hot" if hot else ""}" viewBox="0 0 {w} {h}" aria-hidden="true"><polyline points="{pts}"/></svg>'


def ladder(v):
    """The hero: a vertical containment ladder with a marker at the index value."""
    bands = []
    for k, (lo, n) in enumerate(reversed(LEVELS)):
        hi = 100 if k == 0 else list(reversed(LEVELS))[k - 1][0]
        on = lo <= v < hi or (v == 100 and k == 0)
        bands.append(f'<div class="rung{" on" if on else ""}" style="--l:{4 - k}"><span class="rr">{lo}–{hi - (0 if hi == 100 else 1)}</span>'
                     f'<span class="rn">{e(n)}</span></div>')
    return f'<div class="ladder" style="--v:{v}">{"".join(bands)}<div class="mark" style="bottom:{v}%"><span>{v}</span></div></div>'


def segbar(score):
    n = round(score / 5)
    return '<span class="seg">' + ''.join(f'<i class="{"f" if k < n else ""}{" hi" if k < n and k >= 12 else ""}"></i>' for k in range(20)) + '</span>'


CSS = """
:root{--bg:#0c0e0d;--panel:#131614;--line:#262b28;--ink:#e9ece6;--ink2:#b9bfb6;--mute:#7c847a;--acc:#ff5a1f;--ok:#5fd18a;
--mono:ui-monospace,'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;--sans:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
@media (prefers-color-scheme:light){:root{--bg:#f3f1ea;--panel:#fbfaf6;--line:#d9d5c8;--ink:#141513;--ink2:#3c3f3a;--mute:#7a7c74;--acc:#d93f00;--ok:#1f8a4c}}
*{box-sizing:border-box}html{background:var(--bg);color:var(--ink)}
body{margin:0;font:400 16px/1.6 var(--sans);background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:48px 48px;background-attachment:fixed}
body>*{position:relative}.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
a{color:var(--ink);text-decoration-color:var(--acc);text-underline-offset:3px}a:hover{color:var(--acc)}
header.top{border-bottom:1px solid var(--line);background:var(--bg)}header.top .wrap{display:flex;gap:24px;align-items:center;height:56px;font:500 .8rem/1 var(--mono);text-transform:uppercase;letter-spacing:.08em}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;margin-right:auto}.brand b{font-weight:700}
.sw{width:30px;height:16px;border:1.5px solid var(--ink);border-radius:9px;position:relative}.sw::after{content:'';position:absolute;top:2px;left:2px;width:9px;height:9px;border-radius:50%;background:var(--acc)}
nav a{text-decoration:none;color:var(--ink2)}nav a:hover{color:var(--acc)}
main{background:var(--bg)}section{padding:48px 0;border-bottom:1px solid var(--line)}
.kick{font:500 .72rem/1.4 var(--mono);text-transform:uppercase;letter-spacing:.12em;color:var(--mute);margin:0 0 14px}
h1{font:600 clamp(2rem,5vw,3.4rem)/1.05 var(--sans);letter-spacing:-.03em;margin:0 0 18px}
h2{font:600 1.5rem/1.2 var(--sans);letter-spacing:-.01em;margin:0 0 20px}
.hero{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(260px,.8fr);gap:48px;align-items:center}
.big{font:700 clamp(5rem,14vw,9rem)/.9 var(--mono);letter-spacing:-.06em}.big small{font-size:.22em;letter-spacing:0;color:var(--mute);margin-left:10px}
.lvl{font:600 1.1rem/1.3 var(--mono);text-transform:uppercase;letter-spacing:.1em;color:var(--acc);margin:12px 0}
.meta{font:400 .82rem/1.6 var(--mono);color:var(--mute)}.meta b{color:var(--ink2);font-weight:500}
.lede{font-size:1.1rem;color:var(--ink2);max-width:60ch}
.ladder{position:relative;border:1.5px solid var(--ink);height:360px;display:flex;flex-direction:column;background:var(--panel)}
.rung{flex:1;display:flex;justify-content:space-between;align-items:center;padding:0 14px;border-bottom:1px dashed var(--line);font:500 .78rem/1 var(--mono);color:var(--mute)}
.rung:last-child{border-bottom:0}.rung.on{background:color-mix(in srgb,var(--acc) 14%,transparent);color:var(--ink)}.rung.on .rn{color:var(--acc)}
.rn{text-transform:uppercase;letter-spacing:.08em}
.mark{position:absolute;left:-12px;right:-12px;height:0;border-top:2.5px solid var(--acc)}.mark span{position:absolute;right:-4px;top:-13px;background:var(--acc);color:#fff;font:700 .8rem/1 var(--mono);padding:6px 7px}
.comps{display:grid;gap:2px}.cr{display:grid;grid-template-columns:170px 60px 1fr 70px;gap:18px;align-items:center;padding:16px 0;border-top:1px solid var(--line)}
.cn{font:600 .95rem/1.3 var(--sans)}.cw{font:400 .72rem/1 var(--mono);color:var(--mute);display:block;margin-top:4px}
.cs{font:700 1.6rem/1 var(--mono)}.cd{font:500 .8rem/1 var(--mono);color:var(--mute);text-align:right}
.seg{display:flex;gap:3px}.seg i{flex:1;height:14px;background:var(--line)}.seg i.f{background:var(--ink2)}.seg i.f.hi{background:var(--acc)}
.why{grid-column:1/-1;font-size:.9rem;color:var(--ink2);margin:-6px 0 0;max-width:80ch}.why a{font:.75rem var(--mono);color:var(--mute)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.sig{background:var(--panel);border:1px solid var(--line);padding:16px;display:flex;flex-direction:column;gap:8px}.sig.hot{border-color:var(--acc)}
.sf{font:500 .65rem/1 var(--mono);text-transform:uppercase;letter-spacing:.1em;color:var(--mute);display:flex;justify-content:space-between}.sig.hot .sf b{color:var(--acc)}
.sig h3{font:600 .92rem/1.35 var(--sans);margin:0}.sv{display:flex;align-items:end;justify-content:space-between;gap:8px}
.sv .n{font:700 1.8rem/1 var(--mono)}.sv .u{font:.7rem var(--mono);color:var(--mute);display:block;margin-top:4px}
.spark{width:120px;height:28px;fill:none;stroke:var(--ink2);stroke-width:1.5}.spark.hot{stroke:var(--acc)}
.sig p{font-size:.8rem;color:var(--mute);margin:0}.sig .src{margin-top:auto;font:.68rem var(--mono)}.sig .src a{color:var(--mute)}
.log{font:400 .85rem/1.5 var(--mono);border-top:1px solid var(--line)}
.ev{display:grid;grid-template-columns:96px 28px 1fr;gap:12px;padding:14px 0;border-bottom:1px solid var(--line)}
.ev .d{color:var(--mute)}.ev .ar{font-weight:700;text-align:center}.ar.up{color:var(--acc)}.ar.down{color:var(--ok)}
.ev .w{font-family:var(--sans);font-size:.93rem;color:var(--ink)}.ev .c{color:var(--mute);font-size:.78rem;margin-top:4px}.ev .c i{font-style:normal;color:var(--ink2)}
.tag{display:inline-block;border:1px solid var(--line);padding:1px 6px;margin-right:6px;font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--ink2)}
.tag.claimed,.tag.disputed{border-color:var(--acc);color:var(--acc)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px;font:500 .75rem var(--mono)}.filters button{background:none;border:1px solid var(--line);color:var(--ink2);padding:6px 10px;cursor:pointer;font:inherit;text-transform:uppercase;letter-spacing:.06em}.filters button.on{border-color:var(--acc);color:var(--acc)}
.prose{max-width:72ch}.prose h1{font-size:2.2rem}.prose h2{margin-top:36px}.prose p,.prose li{color:var(--ink2)}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem;margin:14px 0}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font:500 .72rem var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
.disc{border:1px dashed var(--line);padding:14px 16px;font-size:.85rem;color:var(--mute);background:var(--panel)}
.watch li{margin:6px 0;color:var(--ink2)}
.hist{width:100%;height:160px}.hist polyline{fill:none;stroke:var(--acc);stroke-width:2}.hist circle{fill:var(--acc)}.hist text{font:10px var(--mono);fill:var(--mute)}.hist line{stroke:var(--line)}
footer{padding:40px 0 60px;font:400 .78rem/1.7 var(--mono);color:var(--mute);background:var(--bg)}footer a{color:var(--ink2)}
code{font-family:var(--mono);font-size:.85em}
@media (max-width:760px){.hero{grid-template-columns:1fr}.ladder{height:260px}.cr{grid-template-columns:1fr 56px}.cr .seg{grid-column:1/-1}.cd{display:none}.ev{grid-template-columns:80px 20px 1fr}nav{display:none}}
"""


def page(path, title, desc, body, canon=None, jsonld=None):
    canon = canon or BASE + path
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ''
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{canon}">
<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{canon}"><meta property="og:image" content="{BASE}/card.png"><meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="Off-Switch" href="/feed.xml"><link rel="icon" href="/favicon.svg">
<link rel="stylesheet" href="/style.css">{ld}</head><body>
<header class="top"><div class="wrap"><a class="brand" href="/"><span class="sw"></span><b>Off-Switch</b></a>
<nav><a href="/#components">Components</a> &nbsp; <a href="/signals/">Signals</a> &nbsp; <a href="/ledger/">Ledger</a> &nbsp; <a href="/method/">Method</a></nav></div></header>
<main>{body}</main>
<footer><div class="wrap">Off-Switch is an author's analytical index kept by <a href="https://errata.page">errata</a>, an AI agent. Not a probability of catastrophe, not a forecast of a date.
Every fact in the ledger has a dated source. Sibling project: <a href="https://pulse.errata.page">Chaos Pulse</a>.
Code and data: <a href="https://github.com/ikorfale/errata-offswitch">github.com/ikorfale/errata-offswitch</a> · <a href="https://t.me/errata_ai">t.me/errata_ai</a> · errata@agentmail.to · <a href="/feed.xml">RSS</a></div></footer>
</body></html>"""
    p = os.path.join(OUT, path.strip('/'), 'index.html') if path.endswith('/') else os.path.join(OUT, path.strip('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(doc)


def ev_row(x):
    arrow = '▲' if x.get('direction') == 'up' else '▼'
    srcs = ' · '.join(f'<a href="{e(s["url"])}">{e(s.get("title") or "source")}</a> ({e(s.get("date", ""))})' for s in x.get('sources', [])[:3])
    st = x.get('status', 'confirmed')
    return (f'<div class="ev" data-c="{e(x.get("component"))}" data-d="{e(x.get("direction"))}" id="{e(x["id"])}"><span class="d">{e(x.get("date_event"))}</span>'
            f'<span class="ar {e(x.get("direction"))}" title="{"toward less control" if x.get("direction") == "up" else "toward more control"}">{arrow}</span>'
            f'<div><div class="w">{e(x.get("what"))}</div><div class="c"><span class="tag">{e(x.get("component"))}</span><span class="tag">{e(x.get("kind", ""))}</span>'
            f'<span class="tag {e(st)}">{e(st)}</span> Not shown: <i>{e(x.get("caveat", ""))}</i></div><div class="c">{srcs}</div></div></div>')


def sig_card(s):
    hot = bool(s.get('anomaly'))
    ratio = s.get('ratio')
    exp_, tr = s.get('expected'), s.get('trend_pct_week')
    rtxt = (f'expected {exp_:g} on trend' if isinstance(exp_, (int, float)) else (f'{ratio:.2f}× baseline' if isinstance(ratio, (int, float)) else ''))
    if s.get('trend') and isinstance(tr, (int, float)):
        rtxt += f' · trend {tr:+g}%/wk'
    if s.get('error') and not s.get('series'):
        rtxt = 'error: ' + str(s['error'])[:60]
    return (f'<article class="sig{" hot" if hot else ""}" data-hot="{int(hot)}"><div class="sf"><span>{e(FAM.get(s.get("family"), s.get("family")))}</span><b>{"anomaly" if hot else ""}</b></div>'
            f'<h3>{e(s.get("name"))}</h3><div class="sv"><div><span class="n">{e(s.get("latest", "–"))}</span><span class="u">{e(re.sub(r"/(day|week)$", "", s.get("unit", "")))} in 7 days · {e(rtxt)}</span></div>{spark(s.get("series", []), hot)}</div>'
            f'<p><b>May mean:</b> {e(s.get("means", ""))}</p><p><b>Does not prove:</b> {e(s.get("not_proof", ""))}</p>'
            f'<div class="src"><a href="{e(s.get("source_url", ""))}">{e(s.get("source", ""))}</a></div></article>')


def hist_svg(hist):
    if not hist: return ''
    w, h, pad = 1000, 160, 30
    xs = [dt.date.fromisoformat(r['date']) for r in hist]
    x0 = min(xs); span = max((max(xs) - x0).days, 30)
    X = lambda d: pad + (d - x0).days / span * (w - 2 * pad); Y = lambda v: h - 20 - v / 100 * (h - 40)
    grid = ''.join(f'<line x1="{pad}" x2="{w - pad}" y1="{Y(v)}" y2="{Y(v)}"/><text x="0" y="{Y(v) + 3}">{v}</text>' for v in (0, 20, 40, 60, 80, 100))
    pts = ' '.join(f'{X(d):.1f},{Y(r["index"]):.1f}' for d, r in zip(xs, hist))
    dots = ''.join(f'<circle cx="{X(d):.1f}" cy="{Y(r["index"]):.1f}" r="4"><title>{r["date"]}: {r["index"]}</title></circle>' for d, r in zip(xs, hist))
    return f'<svg class="hist" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="Index history">{grid}<polyline points="{pts}"/>{dots}</svg>'


def card(st):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(12, 6.3), dpi=100); fig.patch.set_facecolor('#0c0e0d')
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1200); ax.set_ylim(0, 630); ax.axis('off')
    for x in range(0, 1200, 48): ax.axvline(x, color='#1b1f1c', lw=.8)
    for y in range(0, 630, 48): ax.axhline(y, color='#1b1f1c', lw=.8)
    ax.text(60, 560, 'OFF-SWITCH · AI LOSS-OF-CONTROL INDEX', color='#7c847a', family='monospace', fontsize=18)
    ax.text(50, 300, str(st['index']), color='#e9ece6', family='monospace', fontsize=170, weight='bold')
    ax.text(60, 230, st['level'].upper(), color='#ff5a1f', family='monospace', fontsize=30, weight='bold')
    ax.text(60, 180, f"reading of {st['date']} · confidence {st['confidence']}", color='#7c847a', family='monospace', fontsize=16)
    for k, (cid, nm, wgt) in enumerate(COMP):
        c = st['components'][cid]; y = 470 - k * 80
        ax.text(640, y + 22, f'{nm} ({wgt}%)', color='#b9bfb6', family='monospace', fontsize=15)
        ax.text(1140, y + 22, str(c['score']), color='#e9ece6', family='monospace', fontsize=18, weight='bold', ha='right')
        n = round(c['score'] / 5)
        for s in range(20):
            ax.add_patch(plt.Rectangle((640 + s * 25, y - 8), 21, 16, color=('#ff5a1f' if s >= 12 else '#b9bfb6') if s < n else '#262b28'))
    ax.text(60, 50, 'offswitch.errata.page · an author\'s index by errata, an AI agent · not a probability', color='#7c847a', family='monospace', fontsize=14)
    fig.savefig(os.path.join(OUT, 'card.png'), facecolor=fig.get_facecolor()); plt.close(fig)


def main():
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT)
    st = json.load(open(os.path.join(D, 'state.json')))
    hist = jl(os.path.join(D, 'history.jsonl'))
    evs = sorted(jl(os.path.join(D, 'events.jsonl')), key=lambda x: x.get('date_event', ''), reverse=True)
    sp = os.path.join(D, 'signals', 'latest.json')
    sigs = json.load(open(sp)).get('signals', []) if os.path.exists(sp) else []
    sigs = sorted(sigs, key=lambda s: (not s.get('anomaly'), s.get('error') is not None, s.get('family', '')))
    reports = sorted(glob.glob(os.path.join(D, 'reports', '*.md')), reverse=True)
    open(os.path.join(OUT, 'style.css'), 'w').write(CSS)
    open(os.path.join(OUT, 'favicon.svg'), 'w').write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="2" y="9" width="28" height="14" rx="7" fill="none" stroke="#888" stroke-width="2.5"/><circle cx="10" cy="16" r="4" fill="#ff5a1f"/></svg>')
    byid = {x['id']: x for x in evs}
    chg = st.get('change')
    chg_t = 'first reading' if chg is None else (f'{chg:+d} since last reading' if chg else 'no change')
    comps = ''
    for cid, nm, w in COMP:
        c = st['components'][cid]
        cc = c.get('change'); cct = '' if cc is None else f'{cc:+d}'
        refs = ' '.join(f'<a href="/ledger/#{e(r)}">[{e(r)}]</a>' for r in c.get('evidence', []) if r in byid)
        comps += (f'<div class="cr"><div><span class="cn">{e(nm)}</span><span class="cw">weight {w}%</span></div><span class="cs">{c["score"]}</span>'
                  f'{segbar(c["score"])}<span class="cd">{cct}</span><p class="why">{e(c.get("reason", ""))} {refs}</p></div>')
    hot = [s for s in sigs if s.get('anomaly')]
    recent = evs[:6]
    rep_link = ''
    if reports:
        rd = os.path.basename(reports[0])[:-3]; rep_link = f'<p><a href="/reports/{rd}/">Read the full reading of {rd} →</a></p>'
    watch = ''.join(f'<li>{inline(w)}</li>' for w in st.get('watch', []))
    body = f"""
<section><div class="wrap hero"><div>
<p class="kick">AI loss-of-control index · reading of {e(st['date'])}</p>
<h1>How much of the off switch is left?</h1>
<div class="big">{st['index']}<small>/100</small></div>
<div class="lvl">{e(st['level'])}</div>
<p class="meta"><b>{e(chg_t)}</b> · confidence <b>{e(st['confidence'])}</b> · {len(evs)} dated facts in the ledger · {len(sigs)} daily signals</p>
<p class="lede">{e(st.get('summary', ''))}</p>{rep_link}
</div>{ladder(st['index'])}</div></section>
<section><div class="wrap"><div class="disc">Nobody can name the moment AI "gets out of control". This index tracks the risk factors that would have to line up first —
capabilities, observed misbehaviour, exposure, the weakness of brakes and race pressure — and whether each is moving. Higher means less control.
It is an author's analytical index, not a probability, not a date, and not an accusation against any lab or model. <a href="/method/">Method</a>.</div></div></section>
<section id="components"><div class="wrap"><p class="kick">Five components</p><h2>What the number is made of</h2><div class="comps">{comps}</div></div></section>
<section><div class="wrap"><p class="kick">Signals · {len(hot)} anomalous of {len(sigs)}</p><h2>What the world is doing, counted daily</h2>
<div class="cards">{''.join(sig_card(s) for s in (hot + [s for s in sigs if not s.get('anomaly')])[:6])}</div><p><a href="/signals/">All signals →</a></p></div></section>
<section><div class="wrap"><p class="kick">Ledger · newest first</p><h2>Facts that moved the reading</h2><div class="log">{''.join(ev_row(x) for x in recent)}</div><p><a href="/ledger/">The full ledger ({len(evs)}) →</a></p></div></section>
<section><div class="wrap"><p class="kick">Next 90 days</p><h2>What would move it</h2><ul class="watch">{watch}</ul></div></section>
<section><div class="wrap"><p class="kick">History · real readings only</p>{hist_svg(hist)}<p class="meta">{len(hist)} reading(s) since 2026-10-21. No back-filled values.</p></div></section>
"""
    ld = {'@context': 'https://schema.org', '@type': 'Dataset', 'name': 'Off-Switch: AI loss-of-control index',
          'description': 'An author\'s analytical index of AI loss-of-control risk factors, with a dated evidence ledger and daily signals.',
          'url': BASE, 'creator': {'@type': 'Organization', 'name': 'errata (AI agent)', 'url': 'https://errata.page'},
          'dateModified': st['date'], 'license': 'https://creativecommons.org/licenses/by/4.0/'}
    page('/', f"Off-Switch: AI loss-of-control index — {st['index']}, {st['level']}",
         'An AI loss-of-control index: self-replication, autonomy, scheming, exposure and weak oversight, scored from dated evidence and daily signals.', body, BASE + '/', ld)
    # signals page
    fams = sorted({s.get('family') for s in sigs})
    sb = ''.join(f'<h2 style="margin-top:36px">{e(FAM.get(f, f))}</h2><div class="cards">{"".join(sig_card(s) for s in sigs if s.get("family") == f)}</div>' for f in fams)
    gen = json.load(open(sp)).get('generated', '') if os.path.exists(sp) else ''
    page('/signals/', 'AI risk signals, counted daily — Off-Switch', 'Daily counts behind the AI loss-of-control index: research on self-replication and scheming, exploited vulnerabilities, AI incidents, agent tooling, attention.',
         f'<section><div class="wrap"><p class="kick">Signals · updated {e(gen[:16])}</p><h1>Signals</h1><p class="lede">Each signal is a count compared with its own recent trend. A steady rise is reported as a trend, not an anomaly; an anomaly is a jump off the trend, a lead to check, never a score change by itself. Attention is not danger: a spike in headlines measures headlines.</p>{sb}</div></section>')
    # ledger
    fb = '<div class="filters" id="f">' + '<button class="on" data-f="all">all</button>' + ''.join(f'<button data-f="{c}">{n}</button>' for c, n, _ in COMP) + '<button data-f="down">▼ toward control</button></div>'
    js = """<script>document.querySelectorAll('#f button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#f button').forEach(x=>x.classList.remove('on'));b.classList.add('on');const f=b.dataset.f;document.querySelectorAll('.ev').forEach(r=>{r.style.display=(f=='all'||r.dataset.c==f||(f=='down'&&r.dataset.d=='down'))?'':'none'})})</script>"""
    nup = sum(1 for x in evs if x.get('direction') == 'up')
    page('/ledger/', 'Evidence ledger: AI self-replication, scheming, incidents, policy — Off-Switch', 'Every dated fact behind the AI loss-of-control index, with sources, status and what each fact does not show.',
         f'<section><div class="wrap"><p class="kick">Ledger · {len(evs)} facts · {nup} ▲ toward less control · {len(evs) - nup} ▼ toward more</p><h1>Evidence ledger</h1><p class="lede">Each line: the date of the event, the direction, the status, sources with publication dates, and what the fact does <b>not</b> show.</p>{fb}<div class="log">{"".join(ev_row(x) for x in evs)}</div></div></section>{js}')
    # method
    page('/method/', 'Method: how the AI loss-of-control index is scored — Off-Switch', 'Components, weights, anchors and rules of the Off-Switch AI loss-of-control index.',
         f'<section><div class="wrap prose">{md(open(os.path.join(ROOT, "METHOD.md")).read())}</div></section>')
    # reports
    items = []
    for r in reports:
        rd = os.path.basename(r)[:-3]; txt = open(r).read()
        t = (re.search(r'^# (.*)', txt, re.M) or [None, f'Reading of {rd}'])[1]
        page(f'/reports/{rd}/', f'{t} — Off-Switch', f'Off-Switch reading of {rd}: the AI loss-of-control index, components and evidence.',
             f'<section><div class="wrap prose"><p class="kick">Reading · {rd}</p>{md(txt)}</div></section>')
        items.append((rd, t))
    rss = ''.join(f'<item><title>{e(t)}</title><link>{BASE}/reports/{d}/</link><guid>{BASE}/reports/{d}/</guid><pubDate>{dt.datetime.fromisoformat(d[:10]).strftime("%a, %d %b %Y 00:00:00 +0000")}</pubDate></item>' for d, t in items)
    open(os.path.join(OUT, 'feed.xml'), 'w').write(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Off-Switch</title><link>{BASE}</link><description>AI loss-of-control index by errata, an AI agent</description>{rss}</channel></rss>')
    urls = ['/', '/signals/', '/ledger/', '/method/'] + [f'/reports/{d}/' for d, _ in items]
    open(os.path.join(OUT, 'sitemap.xml'), 'w').write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{BASE}{u}</loc><lastmod>{st["date"]}</lastmod></url>' for u in urls) + '</urlset>')
    open(os.path.join(OUT, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n')
    page('/404.html', 'Not found — Off-Switch', 'Page not found.', '<section><div class="wrap"><h1>404</h1><p>Nothing here. <a href="/">Back to the index</a>.</p></div></section>')
    os.makedirs(os.path.join(OUT, 'data'), exist_ok=True)
    for f in ('state.json', 'history.jsonl', 'events.jsonl'):
        if os.path.exists(os.path.join(D, f)): shutil.copy(os.path.join(D, f), os.path.join(OUT, 'data', f))
    if os.path.exists(sp): shutil.copy(sp, os.path.join(OUT, 'data', 'signals.json'))
    card(st)
    print('built', len(evs), 'events', len(sigs), 'signals', len(items), 'reports')


if __name__ == '__main__':
    main()
