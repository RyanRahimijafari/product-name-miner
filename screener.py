#!/usr/bin/env python3
"""
screener.py - the automated first pass of a name screening.

Does the parts that can be checked reliably by code, for the product in your brief:
  * generates candidate names (optional)
  * domain registration by RDAP, for the top-level domains in the brief
  * Apple App Store exact/prefix matches (iTunes Search API), in the brief's storefronts
  * the close-variant list, and ready-made search and trademark-register links

Trademarks, the web and meanings are judged by an agent or by you (playbook.md). Every row
comes out with a PRELIMINARY verdict that must be confirmed or changed.

Standard library only (Python 3.7+).

  python screener.py --init my-brief.json                 # a starter brief to edit
  python screener.py --brief my-brief.json --names Bexima Quorvel Ledge
  python screener.py --brief my-brief.json --generate 30
  python screener.py --brief my-brief.json --names-file candidates.txt --out results.csv
  python screener.py --brief my-brief.json --generate 20 --offline    # no network
"""
import argparse
import csv
import datetime
import itertools
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import brief as briefmod

ITUNES = "https://itunes.apple.com/search?term={}&entity=software&limit=25&country={}"
UA = {"User-Agent": "product-name-miner/1.0 (name research)"}


def http_status(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return None, b""


def rdap(name, tld):
    """registered / not_registered / unknown. not_registered says nothing about price:
    premium names answer 404 too."""
    domain = f"{name.lower()}.{tld}"
    status, _ = http_status(briefmod.RDAP.get(tld, briefmod.RDAP_FALLBACK).format(domain))
    if status is None or status >= 500:
        status, _ = http_status(briefmod.RDAP_FALLBACK.format(domain))
    if status == 200:
        return "registered"
    if status == 404:
        return "not_registered"
    return "unknown"


def title_matches(name, title):
    """The title is the name, or starts with it as a word: "Tellaro: Budget Planner" for
    Tellaro, not "Pandora" for Pan."""
    t, n = title.lower(), name.lower()
    return t.startswith(n) and (len(t) == len(n) or not t[len(n)].isalnum())


def appstore(name, countries):
    """(hits, ok): the App Store titles that are the name, and whether every store
    answered. A store that did not answer is not "no apps"."""
    hits, ok = {}, True
    for country in countries:
        status, body = http_status(ITUNES.format(urllib.parse.quote(name), country))
        try:
            results = json.loads(body).get("results", []) if status == 200 else None
        except ValueError:
            results = None
        if results is None:
            ok = False
            continue
        for r in results:
            title = r.get("trackName", "")
            if title_matches(name, title):
                hits[(title, r.get("sellerName", ""))] = r.get("primaryGenreName", "")
        time.sleep(0.5)
    return [{"title": t, "seller": s, "genre": g} for (t, s), g in hits.items()], ok


def variants(name, limit=12):
    """Spellings that could be taken for the name: one letter dropped, two swapped,
    sound-alikes."""
    n = name.lower()
    out = set()
    for i in range(len(n)):
        out.add(n[:i] + n[i + 1:])
    for i in range(len(n) - 1):
        out.add(n[:i] + n[i + 1] + n[i] + n[i + 2:])
    for a, b in [("c", "k"), ("k", "c"), ("s", "z"), ("z", "s"), ("ph", "f"),
                 ("y", "i"), ("i", "y"), ("o", "oh")]:
        if a in n:
            out.add(n.replace(a, b, 1))
    if n.endswith("e"):
        out.add(n[:-1])
    out.discard(n)
    return sorted(v for v in out if len(v) >= 3)[:limit]


def search_links(name):
    q = urllib.parse.quote
    return {
        "web": f"https://www.bing.com/search?q={q(chr(34) + name + chr(34))}",
        "uspto": "https://tmsearch.uspto.gov/search/search-results",
        "cipo": "https://ised-isde.canada.ca/cipo/trademark-search/srch",
        "ukipo": "https://trademarks.ipo.gov.uk/ipo-tmtext",
        "tmview": "https://www.tmdn.org/tmview/",
        "wipo": "https://branddb.wipo.int/",
        "play": f"https://play.google.com/store/search?q={q(name)}&c=apps",
        "github": f"https://github.com/{q(name)}",
    }


def prefilter(name, brief):
    """No network: (BLOCKED or None, notes)."""
    n = name.lower()
    lo, hi = brief["name_length"]
    notes = []
    if n in brief["banned_names"]:
        return "BLOCKED", ["on the brief's banned list"]
    if brief["block_i_prefix"] and len(name) > 2 and name[0] == "i" and name[1].isupper():
        return "BLOCKED", ["platform-style i-prefix"]
    if any(r in n for r in brief["crowded_roots"]):
        notes.append("crowded root")
    if not lo <= len(n) <= hi:
        notes.append(f"length outside {lo}-{hi}")
    return None, notes


def generate(count, brief, seed=None):
    rng = random.Random(seed)
    lo, hi = brief["name_length"]
    g = brief["generator"]
    pool = [r + e for r, e in itertools.product(g["roots"], g["endings"])]
    pool = [p for p in dict.fromkeys(pool) if lo <= len(p) <= hi
            and not any(c in p for c in brief["crowded_roots"])]
    rng.shuffle(pool)
    return [p.capitalize() for p in pool[:count]]


def preliminary(pre, domains, hits, notes, incomplete, brief):
    if pre == "BLOCKED":
        return "BLOCKED", "pre-filter: " + "; ".join(notes)
    risky = [h for h in hits if h["genre"].lower() in brief["stores"]["risky_genres"]]
    if risky:
        return "BLOCKED", f"App Store: '{risky[0]['title']}' ({risky[0]['genre']})"
    preferred = brief["domains"]["preferred"]
    if domains.get(preferred) == "registered":
        return "PARTIAL", f".{preferred} already registered"
    if hits:
        return "PARTIAL", "same-name apps in other categories"
    if incomplete:
        return "NEEDS_TM_REVIEW", "not checked: " + ", ".join(incomplete) + "; run playbook steps 1-5"
    return "NEEDS_TM_REVIEW", "domain/app-store pass; run playbook steps 3-5"


def screen(name, brief, offline=False):
    pre, notes = prefilter(name, brief)
    tlds = brief["domains"]["tlds"]
    domains, hits, incomplete = {}, [], []
    use_store = brief["stores"]["app_store"]
    if pre != "BLOCKED":
        if offline:
            incomplete += ["domains"] + (["app store"] if use_store else [])
        else:
            for tld in tlds:
                domains[tld] = rdap(name, tld)
                time.sleep(0.3)
            if "unknown" in domains.values():
                incomplete.append("domains (" + ", ".join(
                    "." + t for t, v in domains.items() if v == "unknown") + ")")
            if use_store:
                hits, ok = appstore(name, brief["stores"]["countries"])
                if not ok:
                    incomplete.append("app store")
    verdict, why = preliminary(pre, domains, hits, notes, incomplete, brief)
    row = {"name": name, "verdict": verdict, "deciding_factor": why}
    for tld in tlds:
        row[f"domain_{tld}"] = domains.get(tld, "not_checked")
    row.update({
        "domain_price_note": "check price at registrar",
        "appstore_exact_hits": "; ".join(f"{h['title']} [{h['genre']}] by {h['seller']}"
                                         for h in hits),
        "tm_live_related": "",
        "tm_dead": "",
        "similar_names": " ".join(variants(name)),
        "meaning_notes": "",
        "prefilter_notes": "; ".join(notes),
        "checks_incomplete": "; ".join(incomplete + ["trademarks", "web", "meaning"]),
        "sources": " ".join(search_links(name).values()),
        "checked_on": datetime.date.today().isoformat(),
    })
    return row


def load_known(paths):
    """Lowercased names already screened (INCOMPLETE ones are screened again)."""
    known = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                known |= {r["name"].lower() for r in (json.loads(l) for l in f if l.strip())
                          if r.get("verdict") != "INCOMPLETE"}
        except FileNotFoundError:
            pass
    return known


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--init", metavar="FILE", help="write a starter brief to FILE and stop")
    ap.add_argument("--brief", help="your product's brief (JSON)")
    ap.add_argument("--data", help="folder for screening data (default: beside the brief)")
    ap.add_argument("--names", nargs="*", default=[])
    ap.add_argument("--names-file")
    ap.add_argument("--generate", type=int, default=0)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out", help="CSV to write (default: results.csv in the data folder)")
    ap.add_argument("--offline", action="store_true", help="pre-filter only, no network")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if args.init:
        briefmod.init(args.init)
        print(f"Wrote {args.init}. Edit it for your product, then pass it as --brief.")
        return
    if not args.brief:
        ap.error("give --brief FILE (or --init FILE to write a starter)")
    brief = briefmod.load(args.brief)
    data = briefmod.data_dir(brief, args.data)

    names = list(args.names)
    if args.names_file:
        with open(args.names_file, encoding="utf-8") as f:
            names += [line.strip() for line in f if line.strip()]
    names += generate(args.generate, brief, args.seed)
    names = list(dict.fromkeys(names))
    known = load_known([os.path.join(data, "screened.jsonl"), os.path.join(data, "results.jsonl")])
    skipped = [n for n in names if n.lower() in known]
    names = [n for n in names if n.lower() not in known]
    if skipped:
        print("Already screened:", ", ".join(skipped))
    if not names:
        ap.error("no names left to screen: give --names, --names-file or --generate")

    rows = []
    for n in names:
        row = screen(n, brief, args.offline)
        rows.append(row)
        print(f"{row['verdict']:<16} {n:<12} {row['deciding_factor']}")

    out = args.out or os.path.join(data, "results.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
