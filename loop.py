#!/usr/bin/env python3
"""
loop.py - keeps a local model screening names for your brief until you stop it (Ctrl+C).

Each round:
  1. the model proposes new names (topped up from screener.py's generator),
  2. screener.py checks domains and the Apple App Store,
  3. each name that passes gets a research session: the model searches
     DuckDuckGo and reads pages with tools, following prompt.md and
     playbook.md (both filled in from your brief), and records a verdict,
  4. the verdict goes to screened.jsonl (so no name is screened twice), the
     full row to results.jsonl and the session's transcript to runs/, all in the
     brief's data folder.

Works with any OpenAI-compatible server: LM Studio, Ollama, llama.cpp.
Standard library only. Stopping loses only the name in progress.

Usage (from any folder):
  python loop.py --brief my-brief.json                       # find the server, run forever
  python loop.py --brief my-brief.json --names Tellaro Bexima # these first, then keep going
  python loop.py --brief my-brief.json --rounds 1 --batch 3  # one short round, as a test
  python loop.py --brief my-brief.json --until 08:00         # run until 8 am
  python loop.py --brief my-brief.json --base-url http://localhost:11434/v1 --model qwen3:27b
"""
import argparse
import datetime
import html
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brief as briefmod  # noqa: E402
import screener as ns  # noqa: E402

try:  # optional: searches that survive DuckDuckGo's rate limit
    from ddgs import DDGS
except ImportError:
    DDGS = None

# Set from the brief's data folder in main(); the functions below read them at call time.
SEED = RESULTS = RUNS = None
BRIEF = None
REGION = "us-en"
SERVERS = ["http://localhost:1234/v1",     # LM Studio
           "http://localhost:11434/v1",    # Ollama
           "http://localhost:8080/v1"]     # llama.cpp
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9"}
DDG = "https://html.duckduckgo.com/html/"
MIN_SEARCHES = 6      # before a CLEAR or PARTIAL is accepted
PAGE_CHARS = 5000     # of a fetched page given to the model

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web with DuckDuckGo. Quotes and site: work.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "fetch_page",
        "description": "Read a web page as text. With focus, only the parts around that word.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
            "focus": {"type": "string", "description": "optional word to look for"}},
            "required": ["url"]}}},
]
RECORD = {"type": "function", "function": {
    "name": "record_verdict",
    "description": "Record the final verdict for this name. Ends the name.",
    "parameters": {"type": "object", "properties": {
        "verdict": {"type": "string", "enum": ["CLEAR", "PARTIAL", "BLOCKED"]},
        "deciding_factor": {"type": "string", "description": "one sentence"},
        "google_play_hits": {"type": "string"},
        "web_hits": {"type": "string", "description": "who uses the name, what they sell"},
        "tm_live_related": {"type": "string"},
        "tm_dead": {"type": "string"},
        "similar_names": {"type": "string", "description": "variants checked and what they hit"},
        "meaning_notes": {"type": "string"},
        "checks_incomplete": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}}},
        "required": ["verdict", "deciding_factor", "sources"]}}}

FINISH = ("Stop searching now. Call record_verdict with what you found, and list every "
          "check you did not finish in checks_incomplete.")


def log(*parts):
    line = " ".join([time.strftime("%H:%M:%S")] + [str(p) for p in parts])
    print(line, flush=True)
    try:
        os.makedirs(RUNS, exist_ok=True)
        with open(os.path.join(RUNS, "loop.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d ") + line + "\n")
    except OSError:
        pass


# --- the model server ---------------------------------------------------------

class ModelError(Exception):
    """The server refused the request itself (e.g. the context is full)."""


def get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def find_server(base, model, context):
    """(base url, model id, context tokens). Prefers a loaded chat model."""
    for b in [base.rstrip("/")] if base else SERVERS:
        try:
            ids = [m["id"] for m in get_json(b + "/models")["data"]]
        except Exception:
            continue
        loaded, ctx = [], {}
        try:  # LM Studio says which models are loaded and with how much context
            for m in get_json(b.rsplit("/v1", 1)[0] + "/api/v0/models")["data"]:
                ctx[m["id"]] = m.get("loaded_context_length")
                if m.get("state") == "loaded" and m.get("type") != "embeddings":
                    loaded.append(m["id"])
        except Exception:
            pass
        chat = [i for i in ids if "embed" not in i.lower()]
        pick = model or next(iter(
            [i for i in loaded if "qwen" in i.lower()] + loaded +
            [i for i in chat if "qwen" in i.lower()] + chat), None)
        if pick:
            return b, pick, context or ctx.get(pick) or 32768
    sys.exit("No model server found at " + ", ".join([base] if base else SERVERS) +
             ". Start LM Studio's server (Developer tab) or Ollama, or pass --base-url.")


def interruptible(fn):
    """fn() with Ctrl+C working while it waits: on Windows a blocking request ignores it
    until the model answers, which can take minutes."""
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # handed back to the caller's thread
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    while t.is_alive():
        t.join(0.3)
    if "error" in box:
        raise box["error"]
    return box["value"]


class Model:
    def __init__(self, base, model):
        self.base, self.model = base, model

    def chat(self, messages, tools=None, temperature=0.3):
        """(message, usage). Waits out a server that is down or busy; never gives up."""
        body = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
        data = json.dumps(body).encode()
        wait = 10
        while True:
            req = urllib.request.Request(self.base + "/chat/completions", data=data,
                                         headers={"Content-Type": "application/json"})
            try:
                d = interruptible(lambda: json.load(urllib.request.urlopen(req, timeout=900)))
                return d["choices"][0]["message"], d.get("usage") or {}
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    raise ModelError(f"{e.code} {e.read()[:300].decode('utf-8', 'replace')}")
                err = f"HTTP {e.code}"
            except (OSError, ValueError, KeyError, IndexError) as e:
                err = str(e) or type(e).__name__
            log(f"model server: {err}; trying again in {wait}s")
            time.sleep(wait)
            wait = min(wait * 2, 300)


def strip_think(text):
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


# --- the web tools ------------------------------------------------------------

def clean(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


_last_search = [0.0]


def web_search(query, n=8):
    """[(title, url, snippet)], or None if no search engine would answer.

    With the ddgs package installed (pip install ddgs) it tries DuckDuckGo, then
    other engines when one blocks; without it, DuckDuckGo's HTML page only, which
    blocks a loop after a few dozen searches."""
    time.sleep(max(0.0, 2.5 - (time.time() - _last_search[0])))
    _last_search[0] = time.time()
    if DDGS:
        for attempt in range(2):
            try:
                return [(r.get("title", ""), r.get("href", ""), r.get("body", ""))
                        for r in DDGS().text(query, region=REGION, max_results=n)][:n]
            except Exception as e:
                if "no results" in str(e).lower():
                    return []
                log(f"  search engines: {type(e).__name__}: {str(e)[:120]}")
                if attempt == 0:
                    time.sleep(20)
        return None  # DuckDuckGo's own page would only be blocked too
    for attempt in range(3):
        if attempt:
            time.sleep(15 * attempt)  # rate-limited (202 or a challenge page)
        _last_search[0] = time.time()
        req = urllib.request.Request(DDG, data=urllib.parse.urlencode({"q": query}).encode(),
                                     headers=dict(BROWSER, Referer="https://html.duckduckgo.com/"))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status, page = r.status, r.read().decode("utf-8", "replace")
        except Exception:
            status, page = None, ""
        if status == 200 and "result__a" in page:
            out = []
            for chunk in page.split('class="result__a"')[1:]:
                href = re.search(r'href="([^"]+)"', chunk)
                title = re.search(r">(.*?)</a>", chunk, re.S)
                snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', chunk, re.S)
                if not href:
                    continue
                url = html.unescape(href.group(1))
                if url.startswith("//duckduckgo.com/l/"):  # older redirect links
                    url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("uddg", [url])[0]
                if "duckduckgo.com/y.js" in url:  # an ad
                    continue
                out.append((clean(title.group(1)) if title else "", url,
                            clean(snip.group(1)) if snip else ""))
            return out[:n]
        if status == 200 and "no-results" in page:
            return []
    return None


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "article", "td"}

    def __init__(self):
        super().__init__()
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def fetch_page(url, focus=None):
    """(text for the model, the final URL or None)."""
    if not re.match(r"https?://", url or ""):
        return "Error: give a full http(s) URL.", None
    try:
        req = urllib.request.Request(url, headers=BROWSER)
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get("Content-Type", "")
            raw, final = r.read(3_000_000), r.geturl()
    except urllib.error.HTTPError as e:
        return f"Could not open {url}: HTTP {e.code}. That check is not done.", None
    except Exception as e:
        return f"Could not open {url}: {e}. That check is not done.", None
    if "html" not in ctype and "text" not in ctype and "json" not in ctype:
        return f"{url} is not a web page ({ctype or 'unknown type'}); it cannot be read here.", final
    charset = re.search(r"charset=([\w-]+)", ctype)
    try:
        page = raw.decode(charset.group(1) if charset else "utf-8", "replace")
    except LookupError:
        page = raw.decode("utf-8", "replace")
    p = _Text()
    try:
        p.feed(page)
    except Exception:
        pass
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    head = f"Page: {final}\nTitle: {p.title.strip()}\n\n"
    if len(text) < 300:
        return (head + text + "\n\n(Almost no text: the page probably needs JavaScript. "
                "Treat this check as not done.)"), final
    if focus:
        spots = [m.start() for m in re.finditer(re.escape(focus), text, re.I)]
        if not spots:
            return head + f"'{focus}' does not appear on this page ({len(text)} characters).", final
        windows, last = [], -1
        for s in spots:
            if s > last:
                windows.append(text[max(0, s - 400): s + 400])
                last = s + 400
            if sum(map(len, windows)) > PAGE_CHARS:
                break
        return head + f"'{focus}' appears {len(spots)} times; around it:\n\n" + \
            "\n[...]\n".join(windows), final
    more = f"\n\n[... {len(text) - PAGE_CHARS} more characters; use focus]" if len(text) > PAGE_CHARS else ""
    return head + text[:PAGE_CHARS] + more, final


def norm_url(u):
    p = urllib.parse.urlsplit(u.strip())
    return (re.sub(r"^www\.", "", p.netloc.lower()) + p.path.rstrip("/") +
            ("?" + p.query if p.query else ""))


# --- records ------------------------------------------------------------------

def load_known():
    known = set()
    for path in (SEED, RESULTS):
        try:
            with open(path, encoding="utf-8") as f:
                rows = [json.loads(l) for l in f if l.strip()]
            known |= {r["name"].lower() for r in rows if r.get("verdict") != "INCOMPLETE"}
        except FileNotFoundError:
            pass
    return known


def survivors():
    out = []
    try:
        with open(SEED, encoding="utf-8") as f:
            out = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        pass
    return [r["name"] for r in out if r.get("verdict") in ("CLEAR", "PARTIAL")]


def append(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save(row, model_id):
    """Every row goes to agent_results.jsonl; final verdicts also to the seed file."""
    append(RESULTS, row)
    if row["verdict"] in ("CLEAR", "PARTIAL", "BLOCKED"):
        append(SEED, {"name": row["name"], "verdict": row["verdict"],
                      "deciding_factor": row["deciding_factor"],
                      "checked_on": row["checked_on"], "by": model_id})


# --- proposing names ----------------------------------------------------------

def playbook_section(text, number):
    m = re.search(rf"^## {number}\..*?(?=^## |\Z)", text, re.S | re.M)
    return m.group(0).strip() if m else ""


def propose(model, playbook, count, known):
    lo, hi = BRIEF["name_length"]
    """New names: the model's ideas first, the generator's to make up the number."""
    names = []
    prompt = (
        "You invent candidate names for this " + BRIEF["product"]["kind"] + ".\n\n" + playbook_section(playbook, 1) + "\n\n" +
        playbook_section(playbook, 7) + "\n\n"
        f"Rules: {lo}-{hi} letters, letters only, easy to say and to spell after hearing it once, "
        "one obvious spelling. Prefer coined words over dictionary words (plain English "
        f"words are premium-priced on .{BRIEF['domains']['preferred']}). Avoid these roots: " +
        (", ".join(BRIEF["crowded_roots"]) or "none") + ". Never: " +
        (", ".join(sorted(BRIEF["banned_names"])) or "none") +
        (", or a lowercase i + word" if BRIEF["block_i_prefix"] else "") + ".\n\n"
        "Already screened, so do not repeat them or make one-letter variants of them: " +
        ", ".join(sorted(known)[-400:]) + "\n\n"
        "Names that survived so far (more in their spirit is good, variants of them are not): " +
        (", ".join(survivors()[-40:]) or "none yet") + "\n\n"
        f"Reply with only a JSON array of {count} new names, nothing else.")
    try:
        msg, _ = model.chat([{"role": "user", "content": prompt}], temperature=0.9)
        found = re.search(r"\[.*?\]", strip_think(msg.get("content")), re.S)
        for n in json.loads(found.group(0)) if found else []:
            n = str(n).strip()
            if re.fullmatch(r"[A-Za-z]{%d,%d}" % (lo, hi), n) and n.lower() not in known:
                names.append(n.capitalize())
                known = known | {n.lower()}
    except (ModelError, ValueError) as e:
        log(f"name ideas failed ({e}); using the generator")
    pool = [g for g in ns.generate(10_000, BRIEF) if g.lower() not in known]
    random.shuffle(pool)
    names = list(dict.fromkeys(names))[:count]
    return names + pool[:max(0, count - len(names))]


# --- researching one name -----------------------------------------------------

def task(row):
    hits = row["appstore_exact_hits"] or "none"
    domains = ", ".join(f".{t} {row['domain_' + t]}" for t in BRIEF["domains"]["tlds"])
    stores = ("- Apple App Store titles that are the name (" +
              ", ".join(c.upper() for c in BRIEF["stores"]["countries"]) + f"): {hits}\n"
              if BRIEF["stores"]["app_store"] else "")
    return (f"Name: {row['name']}\nToday: {row['checked_on']}\n\n"
            f"Screener results:\n"
            f"- domains: {domains} "
            f"(not_registered says nothing about price)\n" + stores +
            f"- screener's preliminary verdict: {row['verdict']} ({row['deciding_factor']})\n"
            f"- pre-filter notes: {row['prefilter_notes'] or 'none'}\n"
            f"- close variants to consider: {row['similar_names']}\n\n"
            f"Screen {row['name']} with the steps in your instructions, then call record_verdict.")


def vet(v, seen, searches, rejections, finishing):
    """(row fields or None, reply for the model). Rejects what the tools did not show."""
    verdict = str(v.get("verdict", "")).upper()
    if verdict not in ("CLEAR", "PARTIAL", "BLOCKED"):
        return None, "Rejected: verdict must be CLEAR, PARTIAL or BLOCKED."
    if not str(v.get("deciding_factor", "")).strip():
        return None, "Rejected: give the deciding_factor in one sentence."
    sources = v.get("sources") or []
    if isinstance(sources, str):
        sources = sources.split()
    sources = [str(s) for s in sources]
    unknown = [s for s in sources if norm_url(s) not in seen]
    incomplete = v.get("checks_incomplete") or []
    if isinstance(incomplete, str):
        incomplete = [p.strip() for p in incomplete.split(";") if p.strip()]
    if unknown and rejections < 2 and not finishing:
        return None, ("Rejected: these sources did not come from any search result or page you "
                      "opened: " + " ".join(unknown) + ". Use only URLs the tools returned, or "
                      "open them first with fetch_page.")
    if unknown:
        sources = [s for s in sources if s not in unknown]
        incomplete.append("unverified sources dropped: " + " ".join(unknown))
    if verdict == "BLOCKED" and not sources and rejections < 2 and not finishing:
        return None, "Rejected: BLOCKED needs the URL of the page that shows the reason."
    if verdict != "BLOCKED" and searches < MIN_SEARCHES:
        if rejections < 2 and not finishing:
            return None, (f"Rejected: only {searches} searches so far. Do the remaining checks in "
                          "your instructions (Google Play, web, variants, trademark leads, "
                          "meaning) before deciding.")
        verdict = "INCOMPLETE"  # not final: the name is screened again later
        incomplete.append(f"web (only {searches} searches)")
    return {"verdict": verdict,
            "deciding_factor": str(v["deciding_factor"]).strip(),
            "google_play_hits": str(v.get("google_play_hits", "")),
            "web_hits": str(v.get("web_hits", "")),
            "tm_live_related": str(v.get("tm_live_related", "")),
            "tm_dead": str(v.get("tm_dead", "")),
            "similar_names": str(v.get("similar_names", "")),
            "meaning_notes": str(v.get("meaning_notes", "")),
            "checks_incomplete": incomplete,
            "sources": sources}, "Recorded."


def shrink(messages, keep=4):
    """Shortens all but the last few tool results, to make room in the context."""
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    for m in tool_msgs[:-keep]:
        if len(m["content"]) > 400:
            m["content"] = m["content"][:400] + " [...trimmed]"


def research(model, context, row, system, max_steps, model_id):
    """The screener row finished by the model; verdict INCOMPLETE if it never got there."""
    name = row["name"]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task(row)}]
    seen, searches, steps, calls_made = set(), 0, 0, 0
    rejections, nudges, finishing = 0, 0, False
    found, reason, search_fails, search_down = None, "", 0, False

    while found is None:
        calls_made += 1
        if calls_made > max_steps + 15:
            reason = "the model did not record a verdict"
            break
        try:
            msg, usage = model.chat(messages, tools=[RECORD] if finishing else TOOLS + [RECORD])
        except ModelError as e:
            if finishing:
                reason = f"model error: {e}"
                break
            log(f"  {name}: {e}; asking for the verdict")
            finishing = True
            shrink(messages, keep=2)
            messages.append({"role": "user", "content": FINISH})
            continue
        calls = msg.get("tool_calls") or []
        content = strip_think(msg.get("content"))
        reply = {"role": "assistant", "content": content}
        if calls:
            reply["tool_calls"] = calls
        messages.append(reply)

        if not calls:
            m = re.search(r"\{.*\"verdict\".*\}", content, re.S)  # a verdict written as text
            try:
                v = json.loads(m.group(0)) if m else None
            except ValueError:
                v = None
            if v is None:
                nudges += 1
                if nudges > 3:
                    reason = "the model stopped calling tools"
                    break
                messages.append({"role": "user", "content": FINISH if finishing else
                                 "Continue: call a tool, or record_verdict when the checks are done."})
                continue
            found, answer = vet(v, seen, searches, rejections, finishing)
            if found is None:
                rejections += 1
                messages.append({"role": "user", "content": answer})
            continue
        nudges = 0

        for c in calls:
            fn = c.get("function", {}).get("name", "")
            try:
                a = json.loads(c["function"].get("arguments") or "{}")
            except (ValueError, KeyError):
                a = None
            if not isinstance(a, dict):
                result = "Error: the arguments were not valid JSON."
            elif fn == "web_search":
                q = str(a.get("query", ""))
                hits = web_search(q)
                search_fails = search_fails + 1 if hits is None else 0
                searches += hits is not None
                if hits is None:
                    result = "Search failed (no search engine answered). That check is not done."
                elif not hits:
                    result = f"No results for {q}."
                else:
                    seen.update(norm_url(u) for _, u, _ in hits)
                    result = "\n".join(f"{i}. {t}\n   {u}\n   {s}" for i, (t, u, s) in
                                       enumerate(hits, 1))
                log(f"  {name}: search {q}  ({'failed' if hits is None else len(hits)})")
            elif fn == "fetch_page":
                url = str(a.get("url", ""))
                result, final = fetch_page(url, a.get("focus") or None)
                if final:
                    seen.update({norm_url(url), norm_url(final)})
                log(f"  {name}: open {url[:90]}")
            elif fn == "record_verdict":
                found, result = vet(a, seen, searches, rejections, finishing)
                if found is None:
                    rejections += 1
                    log(f"  {name}: verdict sent back ({result[:80]})")
            else:
                result = f"Unknown tool {fn}. Use web_search, fetch_page or record_verdict."
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
            steps += 1
            if found:
                break
            if search_fails >= 3:
                search_down = True
                break
        if search_down:
            reason = "the search engines stopped answering"
            break

        full = usage.get("prompt_tokens", 0) > 0.7 * context
        if found is None and not finishing and (steps >= max_steps or full):
            finishing = True
            if full:
                shrink(messages)
            messages.append({"role": "user", "content": FINISH})

    os.makedirs(os.path.join(RUNS, row["checked_on"]), exist_ok=True)
    with open(os.path.join(RUNS, row["checked_on"], name + ".json"), "w", encoding="utf-8") as f:
        json.dump(messages[1:], f, ensure_ascii=False, indent=1)

    out = dict(row)
    screener_gaps = [g for g in row["checks_incomplete"].split("; ")
                     if g and g not in ("trademarks", "web", "meaning")]
    if found is None:
        out.update(verdict="INCOMPLETE", deciding_factor=reason,
                   checks_incomplete="; ".join(screener_gaps + ["trademarks", "web", "meaning"]))
    else:
        out.update(found)
        out["appstore_exact_hits"] = "; ".join(
            p for p in (row["appstore_exact_hits"],
                        found["google_play_hits"] and "Google Play: " + found["google_play_hits"]) if p)
        out["similar_names"] = found["similar_names"] or row["similar_names"]
        out["checks_incomplete"] = "; ".join(screener_gaps + found["checks_incomplete"])
        out["sources"] = " ".join(found["sources"])
        del out["google_play_hits"]
    out["by"] = model_id
    out["searches"] = searches
    out["search_down"] = search_down
    return out


def wait_for_search():
    """Blocks until a search gets an answer: the engines rate-limit a long run."""
    for wait in (120, 300, 600, 900):
        log(f"searches are not being answered; waiting {wait // 60} min (Ctrl+C stops)")
        time.sleep(wait)
        if web_search('"python" programming language'):
            log("searches work again")
            return
    while not web_search('"python" programming language'):
        log("searches are still not being answered; waiting 15 min")
        time.sleep(900)
    log("searches work again")


# --- the loop -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief", required=True, help="your product's brief (JSON): see brief.example.json")
    ap.add_argument("--data", help="folder for screening data (default: beside the brief)")
    ap.add_argument("--names", nargs="*", default=[], help="screen these first")
    ap.add_argument("--batch", type=int, default=10, help="names per round (default 10)")
    ap.add_argument("--rounds", type=int, default=0, help="stop after this many (default: never)")
    ap.add_argument("--until", metavar="HH:MM",
                    help="stop at this clock time (the next one, e.g. 08:00); the name in "
                         "progress is finished first")
    ap.add_argument("--max-steps", type=int, default=30,
                    help="tool calls per name before the model must decide (default 30)")
    ap.add_argument("--research-app-taken", action="store_true",
                    help="also research names whose preferred domain is registered (default: record "
                         "them PARTIAL without research)")
    ap.add_argument("--base-url", help="OpenAI-compatible server, e.g. http://localhost:1234/v1")
    ap.add_argument("--model", help="model id (default: the loaded Qwen model)")
    ap.add_argument("--context", type=int, help="context length in tokens (LM Studio: found)")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    global SEED, RESULTS, RUNS, BRIEF, REGION
    BRIEF = briefmod.load(args.brief)
    data = briefmod.data_dir(BRIEF, args.data)
    SEED, RESULTS, RUNS = (os.path.join(data, n) for n in ("screened.jsonl", "results.jsonl", "runs"))
    REGION = BRIEF["search_region"]
    BROWSER["Accept-Language"] = BRIEF["accept_language"]
    with open(os.path.join(HERE, "playbook.md"), encoding="utf-8") as f:
        playbook = briefmod.render(f.read(), BRIEF)
    with open(os.path.join(HERE, "prompt.md"), encoding="utf-8") as f:
        system = briefmod.render(f.read(), BRIEF) + "\n\n---\n\n" + playbook
    base, model_id, context = find_server(args.base_url, args.model, args.context)
    model = Model(base, model_id)
    log(f"Model {model_id} at {base}, context {context} tokens. Ctrl+C stops.")
    if not DDGS:
        log("Searching DuckDuckGo directly, which blocks after a few dozen searches. "
            f'Stop (Ctrl+C), run: "{sys.executable}" -m pip install ddgs   then start again.')
    if ":11434" in base and not args.context:
        log("Ollama: make sure the context is at least 16k (OLLAMA_CONTEXT_LENGTH=32768), "
            "or the instructions get cut off.")

    deadline = None
    if args.until:
        try:
            h, m = map(int, args.until.split(":"))
            deadline = datetime.datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
        except ValueError:
            sys.exit("--until wants a time like 08:00")
        if deadline <= datetime.datetime.now():
            deadline += datetime.timedelta(days=1)
        log(f"Will stop at {deadline:%a %H:%M}.")

    def time_up():
        return deadline is not None and datetime.datetime.now() >= deadline

    queue, rounds, tally = list(args.names), 0, {}
    try:
        while (not args.rounds or rounds < args.rounds) and not time_up():
            rounds += 1
            known = load_known()
            names = [n for n in queue if n.lower() not in known] or \
                propose(model, playbook, args.batch, known)
            queue = []
            log(f"Round {rounds}: " + ", ".join(names))
            for name in names:
                if time_up():
                    break
                if name.lower() in load_known():
                    continue
                row = ns.screen(name, BRIEF)
                app_taken = (row["domain_" + BRIEF["domains"]["preferred"]] == "registered"
                             and not args.research_app_taken)
                if row["verdict"] == "BLOCKED" or (row["verdict"] == "PARTIAL" and app_taken):
                    out = dict(row, deciding_factor="screener: " + row["deciding_factor"],
                               by="name_screener", searches=0)
                else:
                    log(f"  {name}: {row['verdict']} from the screener; researching")
                    while True:
                        out = research(model, context, row, system, args.max_steps, model_id)
                        if not out.get("search_down"):
                            break
                        wait_for_search()
                save(out, out["by"])
                tally[out["verdict"]] = tally.get(out["verdict"], 0) + 1
                log(f"{out['verdict']:<10} {name:<10} {out['deciding_factor']}")
            log("So far: " + ", ".join(f"{v} {k}" for k, v in sorted(tally.items())))
    except KeyboardInterrupt:
        print()
        log("Stopped. This run: " + (", ".join(f"{v} {k}" for k, v in sorted(tally.items()))
                                     or "nothing finished"))


if __name__ == "__main__":
    main()
