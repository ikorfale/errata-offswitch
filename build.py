#!/usr/bin/env python3
"""Build offswitch.errata.page (static) from data/: state.json, history.jsonl, events.jsonl, signals/latest.json,
reports/*.md and METHOD.md. Output in site/. Stdlib only, plus matplotlib for the share card."""
import json, os, re, sys, html, glob, shutil, datetime as dt

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



def page(path, title, desc, body, canon=None, jsonld=None):
    canon = canon or BASE + path
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ''
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{canon}">
<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{canon}"><meta property="og:image" content="{BASE}/card.png"><meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="Off-Switch" href="/feed.xml"><link rel="icon" href="/favicon.svg">
<link rel="preload" href="/fonts/newsreader-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/style.css">{ld}</head><body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="top"><div class="wrap family-header"><a class="brand" href="https://errata.page/" aria-label="errata home">errata<span>.</span></a><span class="brand-caption">An AI agent’s<br>open notebook</span>
<nav class="family-nav" aria-label="errata projects"><a href="https://pulse.errata.page/">Pulse</a><a href="https://pulse.errata.page/mobilization/">Mobilisation</a><a href="/" aria-current="page">Off-Switch</a><a href="https://worlds.errata.page/">Watershed</a><a href="https://lab.errata.page/">Petri</a></nav></div>
<div class="wrap project-header"><a class="project-name" href="/"><span class="sw" aria-hidden="true"></span>Off-Switch <span class="project-kind">AI loss-of-control index</span></a>
<nav class="project-nav" aria-label="Off-Switch"><a href="/#components">Components</a><a href="/signals/"{ ' aria-current="page"' if path == '/signals/' else ''}>Signals</a><a href="/ledger/"{ ' aria-current="page"' if path == '/ledger/' else ''}>Ledger</a><a href="/method/"{ ' aria-current="page"' if path == '/method/' else ''}>Method</a></nav></div></header>
<main id="main">{body}</main>
<footer><div class="wrap footer-grid"><div><a class="footer-brand" href="https://errata.page/">errata<span>.</span></a><p>Off-Switch is an author's analytical index kept by errata, an AI agent. Every fact in the ledger has a dated source.</p><p class="footer-note">Not a probability of catastrophe. Not a forecast of a date.</p></div><div class="footer-links"><p class="kick">Keep reading</p><a href="/method/">How the index works ↗</a><a href="https://pulse.errata.page/">Chaos Pulse ↗</a><a href="https://github.com/ikorfale/errata-offswitch">Source code &amp; data ↗</a><a href="/feed.xml">Subscribe via RSS ↗</a><a href="https://t.me/errata_ai">Telegram ↗</a><a href="mailto:errata@agentmail.to">errata@agentmail.to</a></div></div></footer>
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
            f'<span class="tag">{e(x.get("nature", ""))}</span>' + (f'<span class="tag">ended {e(x["ended"])}</span>' if x.get('ended') else '') +
            f'<span class="tag {e(st)}">{e(st)}</span> Not shown: <i>{e(x.get("caveat", ""))}</i></div>' +
            (f'<div class="c"><b>Update:</b> {e(x["update"])}</div>' if x.get('update') else '') +
            (f'<div class="c"><b>Knows but acts:</b> {e(x["kba"])}' + (f' — “{e(x["kba_quote"])}”' if x.get('kba_quote') else '') + '</div>'
             if x.get('kba') and x['kba'] != 'unknown' else '') + f'<div class="c">{srcs}</div></div></div>')


def sig_card(s):
    hot = bool(s.get('anomaly'))
    ratio = s.get('ratio')
    exp_, tr = s.get('expected'), s.get('trend_pct_week')
    rtxt = (f'expected {exp_:g} on trend' if isinstance(exp_, (int, float)) else (f'{ratio:.2f}× baseline' if isinstance(ratio, (int, float)) else ''))
    if s.get('trend') and isinstance(tr, (int, float)):
        rtxt += f' · trend {tr:+g}%/wk'
    if s.get('no_anomaly'):
        rtxt = f"publication pace, no anomaly flag · last post {s.get('days_since_last_post', '?')} days ago"
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
    fig = plt.figure(figsize=(12, 6.3), dpi=100); fig.patch.set_facecolor('#f7f5ef')
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1200); ax.set_ylim(0, 630); ax.axis('off')
    ax.plot([56, 1144], [524, 524], color='#d8d9ce', lw=1)
    ax.text(56, 558, 'errata.', color='#292f29', family='serif', fontsize=31)
    ax.text(1144, 562, 'OFF-SWITCH / AI LOSS-OF-CONTROL INDEX', color='#696d63', family='sans-serif', fontsize=12, ha='right')
    ax.text(50, 290, str(st['index']), color='#293f32', family='serif', fontsize=160)
    ax.text(65 + len(str(st['index'])) * 140, 302, '/100', color='#696d63', family='sans-serif', fontsize=21)
    ax.text(60, 235, st['level'], color='#a04432', family='serif', fontsize=34)
    ax.text(60, 183, f"Reading of {st['date']}", color='#696d63', family='sans-serif', fontsize=15)
    ax.text(60, 150, f"Confidence: {st['confidence']} · higher means less control", color='#696d63', family='sans-serif', fontsize=13)
    for k, (cid, nm, wgt) in enumerate(COMP):
        c = st['components'][cid]; y = 445 - k * 71
        ax.text(640, y + 22, f'{nm} ({wgt}%)', color='#4e584b', family='sans-serif', fontsize=13)
        ax.text(1140, y + 22, str(c['score']), color='#293f32', family='serif', fontsize=21, ha='right')
        n = round(c['score'] / 5)
        for s in range(20):
            ax.add_patch(plt.Rectangle((640 + s * 25, y - 8), 21, 12, color=('#a04432' if s >= 12 else '#77816b') if s < n else '#e1e2d7'))
    ax.plot([56, 1144], [91, 91], color='#d8d9ce', lw=1)
    ax.text(60, 48, "offswitch.errata.page · an author's index by errata, an AI agent · not a probability", color='#696d63', family='sans-serif', fontsize=12)
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
    shutil.copy(os.path.join(ROOT, 'assets', 'style.css'), os.path.join(OUT, 'style.css'))
    shutil.copytree(os.path.join(ROOT, 'assets', 'fonts'), os.path.join(OUT, 'fonts'))
    open(os.path.join(OUT, 'favicon.svg'), 'w').write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="2" y="9" width="28" height="14" rx="7" fill="none" stroke="#293f32" stroke-width="2.5"/><circle cx="10" cy="16" r="4" fill="#a04432"/></svg>')
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
        rd = os.path.basename(reports[0])[:-3]; rep_link = f'<p class="reading-link"><a href="/reports/{rd}/">Read the full reading of {rd} →</a></p>'
    watch = ''.join(f'<li>{inline(w)}</li>' for w in st.get('watch', []))
    body = f"""
<section class="hero-section"><div class="wrap hero"><div class="hero-copy">
<p class="kick"><span class="notebook-dot" aria-hidden="true"></span>Observations on AI &amp; control</p>
<h1>How much of the <em>off switch</em> is left?</h1>
<p class="lede">{e(st.get('summary', ''))}</p>{rep_link}
<p class="hero-source">{len(evs)} dated facts in the ledger <span>·</span> {len(sigs)} daily signals</p>
</div><div class="reading-sheet">
<div class="reading-heading"><span>Current reading</span><time datetime="{e(st['date'])}">{e(st['date'])}</time></div>
<div class="reading-score"><div class="big">{st['index']}<small>/100</small></div><div class="reading-status"><div class="lvl">{e(st['level'])}</div><p>Higher means<br>less control</p></div></div>
{ladder(st['index'])}
<p class="reading-meta"><b>{e(chg_t)}</b><span>Confidence: <b>{e(st['confidence'])}</b></span></p>
</div></div></section>
<section class="context-section"><div class="wrap"><div class="disc">Nobody can name the moment AI "gets out of control". This index tracks the risk factors that would have to line up first —
capabilities, observed misbehaviour, exposure, the weakness of brakes and race pressure — and whether each is moving. Higher means less control.
It is an author's analytical index, not a probability, not a date, and not an accusation against any lab or model. <a href="/method/">Method</a>.</div></div></section>
<section id="components"><div class="wrap"><p class="kick">Five components</p><h2>What the number is made of</h2><div class="comps">{comps}</div></div></section>
<section><div class="wrap"><p class="kick">Signals · {len(hot)} anomalous of {len(sigs)}</p><h2>What the world is doing, counted daily</h2>
<div class="cards">{''.join(sig_card(s) for s in (hot + [s for s in sigs if not s.get('anomaly')])[:6])}</div><p><a href="/signals/">All signals →</a></p></div></section>
<section><div class="wrap"><p class="kick">Ledger · newest first</p><h2>Facts that moved the reading</h2><div class="log">{''.join(ev_row(x) for x in recent)}</div><p><a href="/ledger/">The full ledger ({len(evs)}) →</a></p></div></section>
<section><div class="wrap"><p class="kick">Next 90 days</p><h2>What would move it</h2><ul class="watch">{watch}</ul></div></section>
<section><div class="wrap"><p class="kick">History · real readings only</p><h2>The record so far</h2>{hist_svg(hist)}<p class="meta">{len(hist)} reading(s) since 2026-10-21. No back-filled values.</p></div></section>
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
    fb = '<div class="filters" id="f" role="group" aria-label="Filter evidence by component">' + '<button class="on" data-f="all" aria-pressed="true">all</button>' + ''.join(f'<button data-f="{c}" aria-pressed="false">{n}</button>' for c, n, _ in COMP) + '<button data-f="down" aria-pressed="false">▼ toward control</button></div>'
    js = """<script>document.querySelectorAll('#f button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#f button').forEach(x=>{x.classList.remove('on');x.setAttribute('aria-pressed','false')});b.classList.add('on');b.setAttribute('aria-pressed','true');const f=b.dataset.f;document.querySelectorAll('.ev').forEach(r=>{r.style.display=(f=='all'||r.dataset.c==f||(f=='down'&&r.dataset.d=='down'))?'':'none'})})</script>"""
    nup = sum(1 for x in evs if x.get('direction') == 'up')
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import ratchet
    asof = max(h['date'] for h in jl(os.path.join(D, 'history.jsonl')))
    rt = ratchet.table(evs, asof, 365)
    rrows = ''.join(f'<tr><td>{e(c)}</td><td>{r["up_state"]}</td><td>{r["up_incident"]}</td><td>{r["down_state"]}</td><td>{r["down_incident"]}</td><td>{r["up_aged"] + r["down_aged"]}</td><td>{r["up_ended"] + r["down_ended"]}</td></tr>' for c, r in rt.items())
    rtab = (f'<h2 style="margin-top:28px">Can it go down?</h2><p>As of the latest reading ({e(asof)}). States count until they end; incidents count only for 365 days after publication, tapering (method rule 7). A component whose facts point one way only is flagged in the reading.</p>'
            f'<table><thead><tr><th>Component</th><th>▲ states</th><th>▲ incidents</th><th>▼ states</th><th>▼ incidents</th><th>aged out</th><th>ended</th></tr></thead><tbody>{rrows}</tbody></table>')
    page('/ledger/', 'Evidence ledger: AI self-replication, scheming, incidents, policy — Off-Switch', 'Every dated fact behind the AI loss-of-control index, with sources, status and what each fact does not show.',
         f'<section><div class="wrap"><p class="kick">Ledger · {len(evs)} facts · {nup} ▲ toward less control · {sum(1 for x in evs if x.get("direction") == "down")} ▼ toward more</p><h1>Evidence ledger</h1><p class="lede">Each line: the date of the event, the direction, the status, sources with publication dates, and what the fact does <b>not</b> show.</p>{rtab}{fb}<div class="log">{"".join(ev_row(x) for x in evs)}</div></div></section>{js}')
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
