#!/usr/bin/env python3
"""ratchet.py — can the index go down? Per component: facts toward less control (up) and toward more (down),
split into states (count until `ended`) and incidents (count only inside the trailing window by date_published,
with a linear taper: weight 1 on publication, 0 at the window's end, so expiries are gradual, not cliffs).
Flags a component with states in one direction only (either direction), and incident rates built on <3 events.
Method rule 7 (2026-10-25, reviewed by a second model).
usage: python3 tools/ratchet.py [--asof YYYY-MM-DD] [--window DAYS] [--md]"""
import argparse, collections, datetime, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTS = ['capability', 'misbehaviour', 'exposure', 'oversight', 'race']


def table(events, asof, window):
    lo = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=window)).isoformat()
    t = {c: collections.Counter() for c in COMPONENTS}
    for x in events:
        c, d, n = x.get('component'), x.get('direction'), x.get('nature')
        if c not in t or d not in ('up', 'down') or x.get('status') == 'refuted':
            continue
        if n not in ('state', 'incident'):
            raise SystemExit(f'event {x["id"]} has no nature (state|incident)')
        if x.get('date_event', '') > asof:
            continue
        if n == 'state' and x.get('ended') and x['ended'] <= asof:
            t[c][d + '_ended'] += 1
            continue
        pub = x.get('date_published') or x.get('date_event', '')
        if n == 'incident' and pub[:10] < lo:
            t[c][d + '_aged'] += 1
            continue
        t[c][f'{d}_{n}'] += 1
        if n == 'incident':
            age = (datetime.date.fromisoformat(asof) - datetime.date.fromisoformat(pub[:10])).days
            t[c][d + '_taper'] += max(0.0, 1 - age / window)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asof', default=datetime.date.today().isoformat())
    ap.add_argument('--window', type=int, default=365)
    ap.add_argument('--md', action='store_true')
    a = ap.parse_args()
    ev = [json.loads(l) for l in open(os.path.join(ROOT, 'data', 'events.jsonl')) if l.strip()]
    t = table(ev, a.asof, a.window)
    cols = ['up_state', 'up_incident', 'down_state', 'down_incident', 'up_aged', 'down_aged', 'up_ended', 'down_ended']
    if a.md:
        print('| component | ▲ state | ▲ incident | ▼ state | ▼ incident | aged out (▲/▼) | ended (▲/▼) |')
        print('|---|---|---|---|---|---|---|')
    else:
        print(f'as of {a.asof}, incidents counted {a.window} days back by publication date, linear taper')
        print(f'{"component":13}' + ''.join(f'{k:>14}' for k in cols))
    flags = []
    for c in COMPONENTS:
        r = t[c]
        if a.md:
            print(f'| {c} | {r["up_state"]} | {r["up_incident"]} ({r["up_taper"]:.1f}) | {r["down_state"]} | {r["down_incident"]} ({r["down_taper"]:.1f}) | {r["up_aged"]}/{r["down_aged"]} | {r["up_ended"]}/{r["down_ended"]} |')
        else:
            print(f'{c:13}' + ''.join(f'{r[k]:>14}' for k in cols) + f'   taper ▲{r["up_taper"]:.1f} ▼{r["down_taper"]:.1f}')
        for a_, b_ in (('up', 'down'), ('down', 'up')):
            if r[a_ + '_state'] and not r[b_ + '_state']:
                flags.append(f'FLAG {c}: {a_}-states but no {b_}-state in force; the reading lists the queries that searched for one')
        k = r['up_incident'] + r['down_incident']
        if 0 < k < 3:
            flags.append(f'NOTE {c}: {k} incident(s) in window; a rate on <3 events does not move the score')
    for f in flags:
        print(f)


if __name__ == '__main__':
    main()
