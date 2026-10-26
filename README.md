# Product Name Miner

Mine candidate names for an app, then screen them before you fall in love with one.

**What it is for, honestly.** It is tuned for naming software apps: the App Store check, the
default trademark classes (9 and 42), the domain and search habits in `playbook.md`. It can
be pointed at other products (a brand, a physical product, a company) through the brief, but
outside apps expect weaker checks and more of the work left to you: it does not search Google
Play, Amazon, retail shelves or social handles by code.

**Expect to tweak it.** The brief, the generator's syllables and themes, the prompt and the
playbook carry general rules of thumb; read them and change what does not fit yours. The search
and register helpers depend on how other people's websites look today, and they will break
when those change (see Limits).

For each name it checks, in the cheapest-first order:

| Check | How | Done by |
|---|---|---|
| Pre-filter (banned names, crowded words, length) | your brief | script |
| Domains (any TLD you list) | RDAP, the registries' own lookup | script |
| Apple App Store title matches | iTunes Search API, the storefronts you list | script |
| Close spellings that could be mistaken for it | one letter off, swapped, sound-alike | script |
| Google Play, the web, GitHub, Product Hunt | search templates | you, an AI agent, or a local model |
| Trademarks (US, Canada, UK, EU, WIPO) | official registers, with helpers for CIPO and WIPO | you or an agent |
| Meaning in the languages of your markets | dictionaries | you or an agent |

Each name ends **CLEAR**, **PARTIAL** (usable, with a risk a human must weigh) or **BLOCKED**,
with the evidence and the sources. The rules in `playbook.md` are the mistakes worth not
making twice.

> **Screening, not legal advice.** A CLEAR here means "nothing found by these checks". Have a
> trademark professional confirm the finalist before you file or spend on branding.

## Three ways to use it

**1. As a Claude Code skill.** Clone into your skills folder and ask Claude to find or check a name:

```
git clone https://github.com/RyanRahimijafari/product-name-miner ~/.claude/skills/product-name-miner
```

Then: *"Find a name for my budgeting app"* or *"Is Zorvanta taken?"* Claude interviews you for the
brief, runs the screener, does the web and register research, and reports the survivors.
`SKILL.md` is the skill's instructions.

**2. By hand, with the scripts.** Python 3.7+, nothing to install.

```
python screener.py --init my-brief.json                   # a starter brief; edit it
python screener.py --brief my-brief.json --names Bexima Quorvel Tellaro
python screener.py --brief my-brief.json --generate 30    # coined candidates from your brief
python brief.py   --brief my-brief.json                   # the playbook for your product
```

Then do the research steps of `playbook.md` for the names that survive.

**3. Unattended, with a local model.** Any OpenAI-compatible server (LM Studio, Ollama, llama.cpp):

```
pip install ddgs                                          # optional: searches survive rate limits
python loop.py --brief my-brief.json                      # until Ctrl+C
python loop.py --brief my-brief.json --until 08:00 --batch 10
```

The model proposes names, the script screens them, and the model researches each survivor with
real searches and page reads. It rejects sources the model did not actually open, records nothing
on no evidence, and waits out search outages. It cannot read the official trademark registers,
so its CLEAR names are marked as unconfirmed there.

**How fast.** On an RTX 5090 with Qwen 3.8 27B (LM Studio), about 300 results in 10 hours, one
overnight run. Each result is a name proposed, screened and researched with real searches, so
search outages and slow sites set the pace as much as the model. A smaller GPU or model is
slower, and a smaller model researches less carefully: check its sources before trusting a
verdict.

## The brief

One JSON file describes your product (`brief.example.json` is a worked example):

| Field | What it does |
|---|---|
| `product` | What it is, who it is for, the markets, what the name must be. Goes into the agent's instructions |
| `related_categories` | Where an exact-name product would block you |
| `banned_names`, `crowded_roots` | Names to refuse outright; word stems too crowded to defend |
| `block_i_prefix` | Refuse iPhone-style `iName` coinages |
| `name_length` | Shortest and longest name |
| `domains` | TLDs to check and the preferred one (a taken preferred domain makes a name PARTIAL) |
| `stores` | App Store on or off, storefront countries, genres that make a same-name app a block |
| `trademarks` | Nice classes where a clash would block you, and the jurisdictions that matter |
| `languages` | Languages checked for a bad meaning |
| `search_region`, `accept_language` | What the search and fetch tools present themselves as |
| `generator` | Syllables and endings for coined names, and prose themes for the model |

Your results are kept in a `<project>-data/` folder beside the brief (`screened.jsonl` for verdicts,
`results.jsonl` for full rows, `runs/` for transcripts). Those folders and `my-brief*.json` are
git-ignored, so your shortlist stays yours.

## Trademark registers

`registers/` reads the Canadian register (CIPO) and WIPO's Global Brand Database with a real
browser (Node 22+ and Edge, Chrome or Chromium). **Run its control search first**: a register
search that fails to run says "no results", which proves nothing. The USPTO blocks scripts: search it
by hand. Do not work around any site's bot check.

## Limits

- RDAP says registered or not, never the price. Premium domains answer "not registered" too.
- The iTunes API sees titles, not what an app does; a human or agent opens the page.
- Web and mirror sites go stale; the playbook says to confirm on the official register.
- It does not check Google Play by code, social handles, or the name's pronunciation.
- Written against the registries and sites as they were in October 2026. Layouts change; the
  controls fail first.

## Tests

```
python -m unittest discover -s tests      # offline
```

## Licence

MIT. See `LICENSE`.
