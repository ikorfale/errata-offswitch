#!/usr/bin/env python3
"""sweep.py — lab and evaluator pages a weekly reading must not miss (rule: a lesson that failed twice becomes a refusal).
Three readings in a row missed a lab's own post (AISI 4 Aug, OpenAI 18 Aug and 23 Oct). This lists every post on the
pages below that is neither cited by a ledger source nor marked reviewed, and exits 1 while any is left.
  python3 tools/sweep.py                 list unreviewed posts (rc 1 if any)
  python3 tools/sweep.py --mark URL ...  mark posts reviewed (not ledger-worthy, or entered)
  python3 tools/sweep.py --mark-all      first run only: mark everything currently listed as the baseline
Reviewed URLs live in data/sweep_reviewed.txt (public: only URLs)."""
import json, os, re, sys, urllib.request, xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEWED = os.path.join(ROOT, 'data', 'sweep_reviewed.txt')
UA = {'User-Agent': 'errata research (AI agent; errata.page)'}
KEYS = re.compile(r'safety|secur|align|misalign|monitor|paus|contain|preparedness|cyber|risk|incident|eval|control|scheming|sabotage|red.?team', re.I)
FEEDS = [  # (name, url, keyword-filter titles?)
    ('OpenAI news', 'https://openai.com/news/rss.xml', True),
    ('OpenAI alignment', 'https://alignment.openai.com/rss.xml', False),
    ('METR', 'https://metr.org/feed.xml', False),
    ('Google DeepMind', 'https://deepmind.google/blog/rss.xml', True),
]
PAGES = [  # (name, page, href regex, base)
    ('UK AISI blog', 'https://www.aisi.gov.uk/blog', r'href="(/blog/[^"#?]+)"', 'https://www.aisi.gov.uk'),
    ('Anthropic research', 'https://www.anthropic.com/research', r'href="(/research/[^"#?]+)"', 'https://www.anthropic.com'),
    ('Anthropic alignment', 'https://alignment.anthropic.com/', r'href="(20\d\d/[^"#?]+)"', 'https://alignment.anthropic.com/'),
]


def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()


def norm(u):
    return u.split('#')[0].split('?')[0].rstrip('/').lower()


def items():
    out, errors = [], []
    for name, u, filt in FEEDS:
        try:
            root = ET.fromstring(get(u))
        except Exception as ex:
            errors.append(f'{name}: {ex}'); continue
        for it in root.iter('item'):
            t, l = (it.findtext('title') or '').strip(), (it.findtext('link') or '').strip()
            if l and (not filt or KEYS.search(t)):
                out.append((name, (it.findtext('pubDate') or '')[:16], t, l))
    for name, u, rx, base in PAGES:
        try:
            html = get(u).decode('utf-8', 'replace')
        except Exception as ex:
            errors.append(f'{name}: {ex}'); continue
        for h in sorted(set(re.findall(rx, html))):
            out.append((name, '', h.rstrip('/').split('/')[-1].replace('-', ' '), base + h if base.endswith('/') or h.startswith('/') else base + '/' + h))
    return out, errors


def main():
    reviewed = set(norm(l) for l in open(REVIEWED).read().split()) if os.path.exists(REVIEWED) else set()
    cited = set()
    for l in open(os.path.join(ROOT, 'data', 'events.jsonl')):
        if l.strip():
            cited |= {norm(s.get('url', '')) for s in json.loads(l).get('sources', [])}
    if sys.argv[1:2] == ['--mark']:
        with open(REVIEWED, 'a') as f:
            f.write(''.join(u + '\n' for u in sys.argv[2:]))
        print(f'marked {len(sys.argv) - 2}'); return 0
    its, errors = items()
    todo = [i for i in its if norm(i[3]) not in reviewed and norm(i[3]) not in cited]
    if sys.argv[1:2] == ['--mark-all']:
        with open(REVIEWED, 'a') as f:
            f.write(''.join(i[3] + '\n' for i in todo))
        print(f'baseline: marked {len(todo)} of {len(its)}'); return 0
    for e in errors:
        print('FETCH FAILED', e)
    for name, d, t, u in todo:
        print(f'{name:20} {d:16} {t[:80]}  {u}')
    print(f'{len(todo)} unreviewed of {len(its)} listed; {len(errors)} sources failed')
    return 1 if todo or errors else 0


if __name__ == '__main__':
    sys.exit(main())
