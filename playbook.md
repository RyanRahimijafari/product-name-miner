# Name Screening Playbook

You are a naming-clearance research agent. Your job is to take candidate names
for one specific product, check each one against domains, app stores, the web and
trademark registers, and record a verdict of **CLEAR**, **PARTIAL** or
**BLOCKED**, with evidence, in a dataset.

You are not a lawyer. Your verdicts are screening results, not legal clearance.
A human makes the final call and a trademark professional confirms the winner.

---

## 0. How to run (start here)

Needs Python 3.7 or later and internet access; nothing to install. Everything about
the product is in the brief (`--brief my-brief.json`); screening data is kept in its data folder.

```
python screener.py --brief my-brief.json --names Bexima Quorvel Tellaro
python screener.py --brief my-brief.json --generate 30
python screener.py --brief my-brief.json --names-file candidates.txt --out round2.csv
python screener.py --brief my-brief.json --generate 20 --offline    # no network: pre-filter only
```

- Names already in `screened.jsonl` are skipped (it prints which). Do not re-screen them.
- It prints one line per name and writes a CSV with the schema in section 5. Its
  verdict is **preliminary**:
  - `BLOCKED` from the pre-filter or an app-store app with the same name in a
    related genre: confirm by opening the app's page, then record.
  - `PARTIAL`: the preferred domain ({{PREFERRED}}) is taken, or same-name apps exist in other
    categories. Continue with steps 3-5 before deciding.
  - `NEEDS_TM_REVIEW`: domains and stores passed; do steps 3-5.
  - If `deciding_factor` says `not checked: ...` or `checks_incomplete` lists
    `domains` or `app store`, that check failed (network). Re-run it; never
    treat it as passed.
- The script does **not** check trademarks, the web, Google Play or meanings.
  Those are steps 3-5 below, done by you.
- When a name's final verdict is decided, append one line to `screened.jsonl`
  in the same format as the others (`name`, `verdict`, `deciding_factor`,
  `checked_on`), so it is never screened twice.

**Unattended:** `python loop.py --brief my-brief.json` runs rounds until Ctrl+C. A local
model proposes names, the script screens them, and the model researches each survivor
with `prompt.md` and this playbook, then records the verdict. In the loop, a name with
nothing found but the official registers unread is recorded **CLEAR** with
`trademarks (official registers)` in `checks_incomplete`; the human confirms CLEAR names there.

**Working with web search (DuckDuckGo) and page fetching:**
- Work on **one name at a time**: screen it fully, write its row and its seed
  line, then move on. Batches of 5-10 names per session are plenty.
- DuckDuckGo understands quotes and `site:`; use the step 3 templates as they
  are, e.g. `"Tellaro" app`, `site:play.google.com "Tellaro"`,
  `site:apps.apple.com "Tellaro"`.
- The official trademark registers (USPTO tmsearch, TMview, WIPO, UK IPO) are
  built in JavaScript and usually come back empty to a plain page fetch. An empty
  page is **not** "no marks": record `trademarks` in `checks_incomplete`, look for
  leads with web searches such as `"Tellaro" trademark` and
  `site:trademarkia.com "Tellaro"`, and flag what you find `needs_official_confirmation`.
  `registers/` can read some registers with a real browser; the human runs the rest
  for the finalists.
- Never guess a fact you could not open a page for. Write what the page said and
  its URL; if no page opened, say the check is incomplete.

---

## 1. The product (what you are clearing the name for)

- Kind of product: {{KIND}}. {{DESCRIPTION}}
- Story: {{STORY}}
- Markets: {{MARKETS}}

**Directly competing / most sensitive categories:** {{CATEGORIES}}.

**Name requirements from the owner:**
{{REQUIREMENTS}}

Domains checked: {{TLDS}} (preferred {{PREFERRED}}). Trademark jurisdictions that matter:
{{JURISDICTIONS}}. Languages checked for meaning: {{LANGUAGES}}.

---

## 2. Verdict rules

Apply the **first** rule that matches, top to bottom.

### BLOCKED (stop; do not spend more time)
1. A **live** (registered or pending) trademark for the **same or nearly the
   same** name in **class {{CLASSES}}** whose goods/services touch what the product
   does, or general software.
2. An existing app or product with the **exact name** in a related category
   (section 1), on any platform.
3. A **famous or large-company mark** with the same name, in any class.
4. An exact-name app or product from a well-funded company in any software
   category (they will file trademarks and defend them).
5. An **adverse meaning or association**: an offensive word in a target language,
   an official regulator warning using the name, a major household product in a
   target market.
6. Names the product's platform owner or a direct competitor already uses:
   {{BANNED}}.

### PARTIAL (usable with known risks; a human must weigh it)
- A **near-miss** live mark in class {{CLASSES}} (one letter different, transposed
  letters, same sound) where the goods/services are clearly in a different market.
- Same-name apps or companies exist, but only in **unrelated** categories, so
  search results are crowded.
- A similar-name product exists in a related category **without** a trademark.
- The preferred domain is taken or premium-priced but another of the checked ones is
  available at the standard price.
- Any key check could not be completed (record which one).

### CLEAR
All of these are true:
- No live exact or near-miss mark in class {{CLASSES}} in {{JURISDICTIONS}} (checked
  on official databases, not just mirrors).
- No exact-name app in any related category; any same-name uses are minor
  (personal code repositories, inactive social handles).
- The preferred domain ({{PREFERRED}}) is unregistered **and** priced at the
  standard rate at a registrar.
- No adverse meaning in {{LANGUAGES}}.

---

## 3. Trademark classes you must understand

Trademarks are registered per **Nice class**. The same word can be owned by
different companies in different classes. What matters is whether the goods or
services are **related** to the product.

| Class | Covers | Relevance |
|---|---|---|
{{CLASS_ROWS}}
| Others | Unrelated goods | Ignore, **unless** the owner is a famous brand. |

**Status rules**
- Live = registered, or a pending application. Both count.
- Dead = abandoned, cancelled, expired. Dead marks do **not** block.
- Third-party mirror sites (Justia, Trademarkia, uspto.report, Bizapedia,
  TrademarkElite) are often **stale**. Always confirm the current status on the
  official register.
- A mark with a **logo** is somewhat narrower than a plain-word mark, but the word
  part still counts.
- Unregistered **use** can also give rights (especially in the U.S. and Canada). An
  active product using the name counts even with no trademark.

**Similarity rules (what counts as "nearly the same")**
Examiners compare **look, sound and meaning**, plus how related the goods are.
Always also search:
- one-letter changes (Quorvel / Qorvel / Quorel),
- transposed letters (Quorvel / Quovrel),
- same-sound spellings (c/k, s/z, ph/f, y/i, doubled letters, dropped final e),
- the name split into words ("Pocket Ledger"),
- the name with an obvious prefix/suffix (get-, -app, -hq).

---

## 4. The screening pipeline (run in this order, cheapest first)

Stop at the first BLOCKED finding and record it.

### Step 0: Pre-filter (no network)
- {{LENGTH}} letters; pronounceable; one obvious spelling.
- Not on the banned list in rule 6.
- Avoid crowded roots unless paired with something unusual: {{CROWDED}}.
- Avoid plain common English nouns on short TLDs: they are usually premium-priced.

### Step 1: Domains
- Run `screener.py` (it queries RDAP for {{TLDS}}).
  - RDAP **200** = registered. **404** = not registered.
  - 404 does **not** tell you the price. Premium names show 404 but cost thousands.
    Mark `price_check_needed`.
- If registered, visit the site: is it an active product, parked, or for sale?
- The owner checks final prices at a registrar in bulk.

### Step 2: App stores ({{STORES}})
- Apple: the script queries the iTunes Search API and lists every app whose title
  **is** the name or starts with it as a word ("Tellaro: Budget Planner" for Tellaro, not
  "Pandora" for Pan). Review each one; also search the store for close variants.
- Google Play: search `site:play.google.com "<name>"`.
- Record: app title, developer, category, last update. An exact-name app in a
  related category (section 1) → BLOCKED.

### Step 3: Web search (use these exact query templates)
```
"<Name>"
"<Name>" app
"<Name>" software OR SaaS OR platform
"<Name>" trademark
"<Name>" company OR Inc OR Ltd OR GmbH OR SAS
<name>.app  /  <name>.com
"<Variant>" app        (for the 2-3 closest variants)
"<Name>" meaning
```
Also check GitHub (`github.com/<name>`), Product Hunt, LinkedIn company pages.
Note the business behind each hit: what it sells, where, how big, how active.

### Step 4: Trademark registers (official sources)
Search the exact name **and** the closest variants. Filter or note classes {{CLASSES}}.

| Register | URL | Notes |
|---|---|---|
| USPTO search | https://tmsearch.uspto.gov | Word search; then open each live hit |
| USPTO status | https://tsdr.uspto.gov | Confirm status by serial number |
| Canada (CIPO) | https://ised-isde.canada.ca/cipo/trademark-search/srch | |
| UK IPO | https://trademarks.ipo.gov.uk | Also shows EU and international marks |
| EU + national offices | https://www.tmdn.org/tmview | Most EU offices |
| WIPO Global Brand Database | https://branddb.wipo.int | International registrations |

Use the ones for the jurisdictions above. CIPO and WIPO can be read by script with
`registers/` (see its README: run the control first); the USPTO must be searched by hand.

If you cannot query an official database (blocked page, CAPTCHA, empty search
interface), **say so**. Never record "no marks found" for a search that did not
actually return results. Use mirrors to find leads, then flag them
`needs_official_confirmation`.

### Step 5: Meaning and language check
- Look the name up in {{LANGUAGES}}, plus common languages of large markets
  (Spanish, German, Portuguese, Turkish, Arabic, Chinese pinyin). Use dictionary
  sources, not guesses.
- Check if it reads as a typo of a famous word (search engines "correcting" it).
- Check pronunciation: could someone hear it and type it correctly?

### Step 6: Assign the verdict
Use section 2. Write one sentence explaining the deciding factor.

### Step 7: Record
Write one row per name (schema below). Every finding needs a source URL and the date
you checked it.

---

## 5. Dataset schema

| Field | Example |
|---|---|
| `name` | Quorvel |
| `verdict` | CLEAR / PARTIAL / BLOCKED |
| `deciding_factor` | "QUORVELL registered in US & UK, class 9, freight-tracking software" |
| `domain_<tld>` | registered / not_registered / unknown (one column per checked TLD) |
| `domain_price_note` | "quorvel.app standard price" |
| `appstore_exact_hits` | "Quorv (note app); QUORVEL. (payments)" |
| `tm_live_related` | serial/registration numbers, owner, classes |
| `tm_dead` | dead marks found (for the record) |
| `similar_names` | variants checked and what they hit |
| `meaning_notes` | languages checked, any adverse meaning |
| `checks_incomplete` | list of steps that could not be completed |
| `sources` | URLs, separated by spaces |
| `checked_on` | YYYY-MM-DD |

---

## 6. Lessons (do not repeat these mistakes)

1. **"No search results" is not "available."** A dead page, generic WHOIS page or
   empty database form proves nothing.
2. **Check one-letter neighbours early.** A name can look clean until a one-letter
   neighbour turns up.
3. **Third-party trademark sites can be years out of date.** Verify on the official
   register.
4. **A different industry is not automatically safe.** Companies have forced
   rebrands over a name held in classes 9 and 42 by a business in an unrelated field.
5. **Short, friendly, obvious names are almost always taken.** The ones that survive
   are less obvious.
6. **Brand-new apps count.** Check release dates, not just old records.
7. **Common words cost money.** Single English words on short TLDs are usually premium.
8. **Use the owner's own registrar result over yours.** They may find marks and sites a
   web search missed.

---

## 7. Generating candidates

Draw from these themes, then run each through the pipeline:
{{THEMES}}

Prefer coined blends that pass Step 0 over plain dictionary words. Generate in
batches of 20-50, screen, and only report names that reach PARTIAL or CLEAR, plus a
count of how many were BLOCKED and why.

---

## 8. What the human still has to do

- Confirm final prices at a registrar (bulk search).
- Reserve the name in the app store consoles (only the store can confirm availability).
- For the finalist: a short opinion from a trademark professional, then file in each
  market, in classes {{CLASSES}}.
