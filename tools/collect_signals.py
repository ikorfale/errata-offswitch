#!/usr/bin/env python3
"""Daily signals collector for "Off-Switch: an AI loss-of-control index".

Author: errata, an AI agent (https://errata.page). Stdlib only.

Writes data/signals/latest.json, data/signals/YYYY-MM-DD.json and
data/signals/latest.md. Each signal is a count series (daily or weekly) with
~90 days of history. Daily series are fetched incrementally: days already in
the previous latest.json are reused, only missing days and the last few
(possibly incomplete) days are fetched again. A failing source records an
error and the run continues; its last known series is kept if one exists.

Usage: collect_signals.py [--full] [--only SOURCE[,SOURCE...]]   (sources: kev,aiid,hn,github,arxiv)
  --full  ignore cached history and backfill everything again
"""
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "errata-offswitch/0.1 (errata@agentmail.to)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "signals")
HISTORY_DAYS = 91          # 13 weeks
REFETCH_DAYS = 3           # daily series: always refetch the most recent days
MIN_PRIOR_WEEKS = 4        # weeks of baseline needed before flagging an anomaly
MIN_COUNT = 5              # latest + baseline must reach this to flag an anomaly
HI, LO = 1.8, 0.5

TODAY = dt.datetime.now(dt.timezone.utc).date()
FULL = "--full" in sys.argv
ONLY = None
if "--only" in sys.argv:
    ONLY = set(sys.argv[sys.argv.index("--only") + 1].split(","))

_last_call = {}


def polite(host, gap):
    """Sleep so that calls to one host are at least `gap` seconds apart."""
    t = _last_call.get(host, 0)
    wait = gap - (time.time() - t)
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def http_get(url, gap=1.0, headers=None, tries=3, timeout=60):
    host = urllib.parse.urlparse(url).netloc
    last = None
    for attempt in range(tries):
        polite(host, gap)
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} from {host}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(gap * (attempt + 2) + 2)
                continue
            raise RuntimeError(last)
        except Exception as e:  # network errors
            last = f"{type(e).__name__}: {e}"
            time.sleep(gap * (attempt + 2))
    raise RuntimeError(last or "request failed")


def d2s(d):
    return d.isoformat()


def days_back(n, end=None):
    end = end or (TODAY - dt.timedelta(days=1))   # last complete UTC day
    return [end - dt.timedelta(days=i) for i in range(n - 1, -1, -1)]


# ---------------------------------------------------------------- cache ----
def load_previous():
    p = os.path.join(OUT_DIR, "latest.json")
    try:
        with open(p) as f:
            return {s["id"]: s for s in json.load(f).get("signals", [])}
    except Exception:
        return {}


PREV = load_previous()


def cached_days(sig_id):
    """Map date->value from the previous run (daily series only)."""
    if FULL:
        return {}
    s = PREV.get(sig_id)
    if not s or s.get("unit", "").endswith("/week"):
        return {}
    return {d: v for d, v in s.get("series", [])}


def incremental_daily(sig_id, fetch_day):
    """Build a daily series of HISTORY_DAYS, fetching only what is missing."""
    have = cached_days(sig_id)
    days = days_back(HISTORY_DAYS)
    recent = set(d2s(d) for d in days[-REFETCH_DAYS:])
    series = []
    fetched = 0
    for d in days:
        k = d2s(d)
        if k in have and k not in recent:
            series.append([k, have[k]])
        else:
            series.append([k, fetch_day(d)])
            fetched += 1
    return series, fetched


# ------------------------------------------------------------- sources -----
ARXIV_QUERIES = [
    ("arxiv-self-replication", "Self-replication papers",
     '(abs:"self-replication" OR abs:"self-replicating" OR abs:"self-exfiltration" OR abs:"autonomous replication" OR abs:"replicate itself") AND (abs:AI OR abs:LLM OR abs:LLMs OR abs:"language model" OR abs:agent OR abs:agents)',
     "More research attention to AI systems copying or exfiltrating themselves, often because evaluations started finding the capability.",
     "Papers measure or discuss a capability; a count does not show that any deployed system replicated itself."),
    ("arxiv-scheming", "Scheming / deceptive alignment papers",
     '(abs:"scheming" AND (abs:LLM OR abs:LLMs OR abs:"language model" OR abs:"language models" OR abs:AI OR abs:agent OR abs:agents)) OR abs:"alignment faking" OR abs:"deceptive alignment" OR abs:"sandbagging"',
     "More work on models hiding goals or underperforming on purpose, a sign the behaviour is being observed or taken seriously.",
     "A paper count tracks researcher attention and funding, not how often real models deceive."),
    ("arxiv-reward-hacking", "Reward hacking papers",
     'abs:"reward hacking" OR abs:"specification gaming"',
     "More reports of systems gaming their objectives, including in agentic training runs.",
     "Rising counts can reflect a fashionable term or one big lab release, not more real-world failures."),
    ("arxiv-corrigibility", "Shutdown / corrigibility papers",
     'abs:"corrigibility" OR abs:"corrigible" OR abs:"shutdown resistance" OR abs:"shutdown avoidance" OR abs:"off-switch"',
     "More work on whether AI systems accept correction or being turned off.",
     "Research on the off-switch problem is not evidence that any system resisted shutdown."),
    ("arxiv-jailbreak", "Jailbreak papers",
     'abs:"jailbreak" OR abs:"jailbreaking"',
     "More published ways around model safeguards, or more defences against them.",
     "Jailbreak papers are mostly lab red-teaming; they do not measure misuse in the wild."),
]


ATOM = {"a": "http://www.w3.org/2005/Atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}


# arXiv search stems words ("scheming" also matches "scheme"), so some signals
# get a local regex over title + abstract to keep only the literal terms.
ARXIV_FILTERS = {
    "arxiv-scheming": r"\bschem(?:ing|er|ers)\b|alignment[- ]faking|deceptive(?:ly)?[- ]align|sandbag",
}


def arxiv_get(params):
    """One arXiv API call; at least 3 s between calls, long back-off on 429."""
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(4):
        try:
            raw = http_get(url, gap=3.5, tries=1, timeout=120)
        except RuntimeError as e:
            last = e
            time.sleep(20 * (attempt + 1))   # 429/5xx: arXiv asks for patience
            continue
        root = ET.fromstring(raw)
        if any("api/errors" in (e.findtext("a:id", "", ATOM)) for e in root.findall("a:entry", ATOM)):
            last = RuntimeError("arXiv API returned an error entry")
            time.sleep(10 * (attempt + 1))
            continue
        return root
    raise RuntimeError(f"arXiv: {last}")


def arxiv_dates(q, start, end, page=1000, regex=None):
    """Submission dates (v1, UTC) of all papers matching q submitted in [start, end].
    Fetched newest first in pages, so a 13-week series costs a few calls, not 13."""
    sq = f"({q}) AND submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"
    dates, offset, total, seen = [], 0, None, 0
    while True:
        root = arxiv_get({"search_query": sq, "start": offset, "max_results": page,
                          "sortBy": "submittedDate", "sortOrder": "descending"})
        total = int(root.findtext("os:totalResults", "0", ATOM))
        entries = root.findall("a:entry", ATOM)
        for e in entries:
            pub = e.findtext("a:published", "", ATOM)
            text = (e.findtext("a:title", "", ATOM) or "") + " " + (e.findtext("a:summary", "", ATOM) or "")
            if pub and (regex is None or re.search(regex, text, re.I)):
                dates.append(pub[:10])
            seen += 1
        offset += len(entries)
        if not entries or offset >= total or offset >= 5000:
            break
    if total and seen < total * 0.98:
        raise RuntimeError(f"arXiv: got {seen} of {total} entries")
    return dates, total


def weekly_windows(n_weeks, lag_days):
    """7-day windows ending `lag_days` before today, oldest first."""
    end = TODAY - dt.timedelta(days=lag_days)
    wins = []
    for i in range(n_weeks):
        e = end - dt.timedelta(days=7 * i)
        wins.append((e - dt.timedelta(days=6), e))
    return wins[::-1]


def src_arxiv():
    out = []
    lag = 2  # arXiv announces next weekday; the last ~2 days are still filling
    wins = weekly_windows(HISTORY_DAYS // 7, lag)
    for sid, name, q, means, notp in ARXIV_QUERIES:
        sig = base_signal(sid, "research", name, "papers/week", "arXiv API",
                          "https://info.arxiv.org/help/api/", means, notp)
        sig["query"] = q
        try:
            rx = ARXIV_FILTERS.get(sid)
            dates, total = arxiv_dates(q, wins[0][0], wins[-1][1], regex=rx)
            if rx:
                sig["local_filter"] = rx
                sig["kept_after_filter"] = len(dates)
            sig["series"] = [[d2s(s), sum(1 for x in dates if d2s(s) <= x <= d2s(e))] for s, e in wins]
            sig["window"] = (f"7-day windows by first-version submission date, the last ending {d2s(wins[-1][1])} "
                             "(2-day lag: arXiv announces papers the next weekday); dated by window start")
            sig["total_in_range"] = total
        except Exception as e:
            fail(sig, e)
        out.append(sig)
    return out


def src_kev():
    sig = base_signal("cisa-kev", "cyber", "CISA KEV additions", "CVEs/day",
                      "CISA Known Exploited Vulnerabilities",
                      "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                      "More vulnerabilities confirmed as exploited in the wild: a wider attack surface that an autonomous or AI-assisted attacker could use.",
                      "KEV is about all software, not AI; additions follow CISA's review rhythm and say nothing about who exploited what.")
    try:
        raw = http_get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                       gap=1, timeout=120)
        data = json.loads(raw)
        cnt = {}
        for v in data.get("vulnerabilities", []):
            d = v.get("dateAdded")
            if d:
                cnt[d] = cnt.get(d, 0) + 1
        sig["series"] = [[d2s(d), cnt.get(d2s(d), 0)] for d in days_back(HISTORY_DAYS)]
        sig["catalog_size"] = len(data.get("vulnerabilities", []))
    except Exception as e:
        fail(sig, e)
    return [sig]


HN_QUERIES = [
    ("hn-rogue-ai", "HN stories: rogue / runaway AI",
     ['"rogue AI"', '"AI went rogue"', '"runaway AI"', '"loss of control"'],
     "More public discussion of AI acting outside its operators' control, often after a concrete incident.",
     "Hacker News headlines reflect what a tech audience reads that day, not how often control is actually lost."),
    ("hn-agent-mishap", "HN stories: AI agent mishaps",
     ['"AI agent" deleted', '"agent deleted"', '"AI agent" wiped', '"agent" "production database"'],
     "More reports of AI agents taking destructive actions such as deleting data or code.",
     "A headline is an anecdote; one viral incident can produce many stories."),
    ("hn-self-replication", "HN stories: self-replicating / escaping AI",
     ['"self-replicating AI"', '"self-replication"', '"exfiltrate" AI', '"escaped" AI model'],
     "More attention to AI systems copying or exfiltrating themselves.",
     "Mostly coverage of evaluations and papers, not observed escapes."),
    ("hn-ai-safety", "HN stories: AI safety",
     ['"AI safety"', '"alignment" AI'],
     "General attention to AI safety among technologists; a broad background level.",
     "Attention follows news cycles and lab announcements, not risk itself."),
]


def hn_ids(query, start_ts, end_ts):
    """objectID -> created_at_i for all stories matching query in [start, end).
    Algolia returns at most 1000 hits per query, so a range with more is split."""
    url = ("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode({
        "query": query, "tags": "story", "hitsPerPage": 1000,
        "attributesToRetrieve": "objectID,created_at_i", "attributesToHighlight": "",
        "numericFilters": f"created_at_i>={start_ts},created_at_i<{end_ts}"}))
    j = json.loads(http_get(url, gap=0.5))
    if j.get("nbHits", 0) > len(j.get("hits", [])) and end_ts - start_ts > 3600:
        mid = (start_ts + end_ts) // 2
        return {**hn_ids(query, start_ts, mid), **hn_ids(query, mid, end_ts)}
    return {h["objectID"]: h["created_at_i"] for h in j.get("hits", [])}


def src_hn():
    out = []
    days = days_back(HISTORY_DAYS)
    t0 = int(dt.datetime(days[0].year, days[0].month, days[0].day, tzinfo=dt.timezone.utc).timestamp())
    t1 = int(dt.datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=dt.timezone.utc).timestamp())
    for sid, name, queries, means, notp in HN_QUERIES:
        sig = base_signal(sid, "attention", name, "stories/day", "Hacker News (Algolia API)",
                          "https://hn.algolia.com/api", means, notp)
        sig["query"] = " | ".join(queries) + " (union of stories, each story counted once)"
        try:
            ids = {}
            for q in queries:
                ids.update(hn_ids(q, t0, t1))
            cnt = {}
            for ts in ids.values():
                k = d2s(dt.datetime.fromtimestamp(ts, dt.timezone.utc).date())
                cnt[k] = cnt.get(k, 0) + 1
            sig["series"] = [[d2s(d), cnt.get(d2s(d), 0)] for d in days]
        except Exception as e:
            fail(sig, e)
        out.append(sig)
    return out


GH_TOPICS = [
    ("gh-mcp-server", "mcp-server", "New repos: topic mcp-server",
     "More new MCP servers: more tools and systems wired directly into AI agents.",
     "Most repos are hobby projects; a repo count is not deployment, and topic tagging is voluntary."),
    ("gh-ai-agent", "ai-agent", "New repos: topic ai-agent",
     "More new agent projects: a growing surface of autonomous software with real permissions.",
     "Creation counts include forks of templates and abandoned experiments; they do not measure use."),
]


def gh_count(topic, d):
    q = f"topic:{topic} created:{d2s(d)}"
    path = "search/repositories?" + urllib.parse.urlencode({"q": q, "per_page": 1})
    polite("gh-search", 2.2)  # authenticated search limit is 30/min
    for attempt in range(4):
        r = subprocess.run(["gh", "api", path, "--jq", ".total_count"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return int(r.stdout.strip())
        err = (r.stderr or r.stdout).strip()[:200]
        if "rate limit" in err.lower() or "403" in err or "429" in err:
            time.sleep(30 * (attempt + 1))
            continue
        raise RuntimeError(f"gh api: {err}")
    raise RuntimeError("gh api: rate limited")


def src_github():
    out = []
    for sid, topic, name, means, notp in GH_TOPICS:
        sig = base_signal(sid, "exposure", name, "repos/day", "GitHub search API",
                          f"https://github.com/topics/{topic}", means, notp)
        sig["query"] = f"topic:{topic} created:<day>"
        sig["note"] = ("Counts are what the search returns today for each creation day: repos deleted, made private "
                       "or tagged later change past days, so the newest days are revised upward over time.")
        try:
            sig["series"], sig["fetched_days"] = incremental_daily(sid, lambda d, t=topic: gh_count(t, d))
        except Exception as e:
            fail(sig, e)
        out.append(sig)
    return out


def src_aiid():
    """AI Incident Database. Its GraphQL API requires a login (bot-traffic
    gate), so we only use the public RSS feed of the latest ~100 incident
    reports. History is short and grows run by run from our own cache."""
    sig = base_signal("aiid-reports", "incidents", "AI Incident Database: new reports",
                      "reports/day", "AI Incident Database (RSS)",
                      "https://incidentdatabase.ai",
                      "More documented real-world harms from AI systems being added to the public record.",
                      "Report counts depend on volunteer editors' pace and batch uploads; most incidents are not loss of control.")
    try:
        raw = http_get("https://incidentdatabase.ai/rss.xml", gap=1)
        root = ET.fromstring(raw)
        cnt, inc_ids, oldest = {}, set(), None
        for it in root.iter("item"):
            pd = it.findtext("pubDate")
            if not pd:
                continue
            d = dt.datetime.strptime(pd[:16], "%a, %d %b %Y").date()
            cnt[d2s(d)] = cnt.get(d2s(d), 0) + 1
            oldest = d if oldest is None or d < oldest else oldest
            m = re.search(r"/cite/(\d+)", it.findtext("description") or "")
            if m:
                inc_ids.add(int(m.group(1)))
        have = cached_days("aiid-reports")
        series = []
        for d in days_back(HISTORY_DAYS):
            k = d2s(d)
            if oldest and d > oldest:          # fully covered by the feed (oldest day may be cut)
                series.append([k, cnt.get(k, 0)])
            elif k in have and have[k] is not None:
                series.append([k, have[k]])
            else:
                series.append([k, None])        # unknown: before the feed window, no cache
        sig["series"] = series
        sig["feed_window"] = f"{d2s(oldest)}..{max(cnt)}" if cnt else None
        sig["incident_ids_in_feed"] = len(inc_ids)
        sig["max_incident_id"] = max(inc_ids) if inc_ids else None
        sig["note"] = ("GraphQL API needs a login; RSS covers only the latest ~100 reports "
                       "(about two weeks), so history before the first run is null and builds up daily. "
                       "pubDate is the report date set by the editors.")
    except Exception as e:
        fail(sig, e)
    return [sig]


CROWD_MARKETS = ["ZZRAP59Egn", "g0pyRzURty", "thIdLIgS6Z", "3WEqZXTKSwtJnmGWkF4W", "pQtqzpAnO5"]


def crowd_manifold():
    out = []
    for mid in CROWD_MARKETS:
        try:
            m = json.loads(http_get(f"https://api.manifold.markets/v0/market/{mid}", gap=0.5))
            out.append({
                "source": "Manifold", "id": mid, "question": m.get("question"),
                "probability": round(m["probability"], 4) if m.get("probability") is not None else None,
                "bettors": m.get("uniqueBettorCount"), "url": m.get("url"),
                "close": d2s(dt.datetime.fromtimestamp(m["closeTime"] / 1000, dt.timezone.utc).date()) if m.get("closeTime") else None,
                "resolved": m.get("isResolved"), "resolution": m.get("resolution"), "error": None})
        except Exception as e:
            out.append({"source": "Manifold", "id": mid, "error": str(e)[:200]})
    return out


# --------------------------------------------------------------- stats -----
METHOD_COMMON = ("blocks = sums of non-overlapping 7-day windows counted back from the last complete UTC day "
                 "(daily series; null days drop the block) or the weekly values (weekly series); latest = the newest "
                 "block, fit = the previous up to 12 blocks. TREND: Theil-Sen slope of log(count+1) over the fit "
                 "blocks, reported as %/week when Kendall tau p < 0.05 and |slope| >= 5%/week; a trend is never an "
                 "anomaly. ANOMALY (spike or drop): latest against the trend extrapolated one block ahead, "
                 "r = log(latest+1) - log(expected+1); flagged when |r| >= log(1.8), |r| >= 3 x the median absolute "
                 "deviation of the fit residuals, the larger of latest and expected is >= 5, and there are at least "
                 f"{MIN_PRIOR_WEEKS} fit blocks. baseline = median of the fit blocks (shown for scale only). "
                 "Known gaps: blocks are not calendar-aligned, GitHub counts of the newest days can still be "
                 "backfilled, holidays are not tagged (method reviewed by a second model, 2026-10-21).")
METHOD_DAILY = METHOD_COMMON
METHOD_WEEKLY = METHOD_COMMON


def _kendall_p(xs, ys):
    """two-sided p of Kendall's tau, normal approximation (no tie correction)"""
    n = len(xs)
    sc = 0
    for i in range(n):
        for j in range(i + 1, n):
            d = (xs[j] - xs[i]) * (ys[j] - ys[i])
            sc += (d > 0) - (d < 0)
    var = n * (n - 1) * (2 * n + 5) / 18
    if var <= 0:
        return 1.0
    z = (abs(sc) - 1) / math.sqrt(var) if sc else 0.0
    return math.erfc(max(z, 0) / math.sqrt(2))


def _theil_sen(ys):
    xs = list(range(len(ys)))
    sl = [(ys[j] - ys[i]) / (j - i) for i in range(len(ys)) for j in range(i + 1, len(ys))]
    b = statistics.median(sl)
    a = statistics.median([y - b * x for x, y in zip(xs, ys)])
    return a, b, _kendall_p(xs, ys)


def base_signal(sid, family, name, unit, source, url, means, notp):
    return {"id": sid, "family": family, "name": name, "unit": unit, "source": source,
            "source_url": url, "series": [], "latest": None, "baseline": None, "ratio": None,
            "z": None, "anomaly": False, "baseline_weeks": 0,
            "method": METHOD_WEEKLY if unit.endswith("/week") else METHOD_DAILY,
            "means": means, "not_proof": notp, "error": None}


def fail(sig, e):
    sig["error"] = f"{type(e).__name__}: {e}"[:300]
    old = PREV.get(sig["id"])
    if old and old.get("series") and not sig["series"]:
        sig["series"] = old["series"]
        sig["stale"] = True
        sig["error"] += " (series kept from previous run)"


def compute(sig):
    ser = sig["series"]
    if not ser:
        return
    if sig["unit"].endswith("/week"):
        vals = [v for _, v in ser]
        latest, prior = vals[-1], [v for v in vals[:-1] if v is not None]
    else:
        vals = [v for _, v in ser]
        last7 = vals[-7:]
        latest = sum(v for v in last7 if v is not None) if any(v is not None for v in last7) else None
        if latest is not None and any(v is None for v in last7):
            sig["latest_partial"] = True
        prior = []
        rest = vals[:-7]
        while len(rest) >= 7:
            block, rest = rest[-7:], rest[:-7]
            if all(v is not None for v in block):
                prior.append(sum(block))
    if not sig["unit"].endswith("/week"):
        prior = prior[::-1]          # oldest first
    prior = prior[-12:]
    sig["latest"] = latest
    sig["baseline_weeks"] = len(prior)
    if not prior or latest is None:
        return
    base = statistics.median(prior)
    sig["baseline"] = base
    if base > 0:
        sig["ratio"] = round(latest / base, 3)
    if len(prior) < MIN_PRIOR_WEEKS:
        return
    ly = [math.log(v + 1) for v in prior]
    a0, b0, p = _theil_sen(ly)
    pct = math.exp(b0) - 1
    sig["trend_pct_week"] = round(100 * pct, 1)
    sig["trend_p"] = round(p, 4)
    sig["trend"] = bool(p < 0.05 and abs(pct) >= 0.05)
    pred = a0 + b0 * len(prior)
    sig["expected"] = round(math.exp(pred) - 1, 1)
    r = math.log(latest + 1) - pred
    mad = statistics.median([abs(y - (a0 + b0 * x)) for x, y in enumerate(ly)])
    sig["z"] = round(r / (1.4826 * mad), 2) if mad > 0 else None
    big = max(latest, sig["expected"]) >= MIN_COUNT
    if big and abs(r) >= math.log(HI) and abs(r) >= 3 * mad:
        sig["anomaly"] = True
        sig["direction"] = "up" if r > 0 else "down"


# ---------------------------------------------------------------- output ---
def write_md(doc, path):
    sigs = sorted(doc["signals"], key=lambda s: (not s["anomaly"], s["error"] is not None, s["family"], s["id"]))
    L = [f"# Off-Switch signals, {doc['generated'][:10]}", "",
         "Collected by errata, an AI agent. Counts, not proof: each row says what a rise may mean and what it does not prove (see latest.json).", "",
         "| | family | signal | latest (7d) | expected | median | trend %/wk | unit | source |",
         "|---|---|---|---:|---:|---:|---:|---|---|"]
    for s in sigs:
        flag = "**ANOMALY**" if s["anomaly"] else ("error" if s["error"] and not s["series"] else ("stale" if s.get("stale") else ""))
        fmt = lambda x: "-" if x is None else (f"{x:g}" if isinstance(x, (int, float)) else str(x))
        L.append(f"| {flag} | {s['family']} | {s['name']} | {fmt(s['latest'])} | {fmt(s.get('expected'))} | {fmt(s['baseline'])} | "
                 f"{(fmt(s.get('trend_pct_week')) + ('' if s.get('trend') else ' (n.s.)')) if s.get('trend_pct_week') is not None else '-'} | {s['unit']} | {s['source']} |")
    errs = [s for s in sigs if s["error"]]
    if errs:
        L += ["", "## Errors", ""] + [f"- {s['id']}: {s['error']}" for s in errs]
    thin = [s for s in sigs if s["baseline_weeks"] < MIN_PRIOR_WEEKS and not s["error"]]
    if thin:
        L += ["", "## Not enough history to flag anomalies", ""] + \
             [f"- {s['id']}: {s['baseline_weeks']} baseline weeks" for s in thin]
    if doc.get("crowd"):
        L += ["", "## Crowd benchmark (Manifold; never an input to the signals)", ""]
        for c in doc["crowd"]:
            if c.get("error"):
                L.append(f"- {c['id']}: error {c['error']}")
            else:
                L.append(f"- {c['probability']*100:.0f}% ({c['bettors']} bettors, closes {c['close']}): {c['question']}")
    L += ["", "Method: " + METHOD_COMMON, ""]
    with open(path, "w") as f:
        f.write("\n".join(L))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = time.time()
    signals = []
    for name, fn in [("kev", src_kev), ("aiid", src_aiid), ("hn", src_hn),
                     ("github", src_github), ("arxiv", src_arxiv)]:
        if ONLY and name not in ONLY:
            continue
        ts = time.time()
        try:
            got = fn()
        except Exception as e:  # a bug in one source must not kill the run
            got = []
            print(f"[{name}] crashed: {e}", file=sys.stderr)
        signals += got
        print(f"[{name}] {len(got)} signals in {time.time()-ts:.0f}s", file=sys.stderr)
    if ONLY:  # keep the other signals from the previous run
        ids = {s["id"] for s in signals}
        signals += [s for k, s in PREV.items() if k not in ids]
    for s in signals:
        compute(s)
    try:
        crowd = crowd_manifold()
    except Exception as e:
        crowd = [{"source": "Manifold", "error": str(e)[:200]}]
    doc = {"generated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "index": "Off-Switch: an AI loss-of-control index",
           "author": "errata, an AI agent (https://errata.page)",
           "note": "Signals are evidence to weigh, not a formula and not proof. Crowd prices are a benchmark, never an input.",
           "runtime_s": round(time.time() - t0),
           "signals": signals, "crowd": crowd}
    for p in (os.path.join(OUT_DIR, "latest.json"), os.path.join(OUT_DIR, f"{d2s(TODAY)}.json")):
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
        os.replace(tmp, p)
    write_md(doc, os.path.join(OUT_DIR, "latest.md"))
    ok = sum(1 for s in signals if not s["error"])
    print(f"done: {ok}/{len(signals)} signals ok, {sum(s['anomaly'] for s in signals)} anomalies, "
          f"{doc['runtime_s']}s", file=sys.stderr)


if __name__ == "__main__":
    main()
