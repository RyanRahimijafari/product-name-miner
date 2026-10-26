---
name: product-name-miner
description: Find and screen names for a product, app, company or project. Use when the user wants name ideas checked, or asks "is this name taken?", "can I use this name?", "find me a name for my app". Generates candidates, then checks domains (RDAP), the Apple App Store, Google Play, the web, trademark registers and meanings, and records a CLEAR / PARTIAL / BLOCKED verdict with sources for each. A screening aid, not legal advice.
---

# Product Name Miner

Screens candidate names for **one product**. Code does what code can check reliably (domains,
App Store titles, close spellings); you do the research a script cannot (web, Google Play,
trademark leads, meaning) and record a verdict with evidence for each name.

Everything runs from the folder this skill is in, with Python 3.7+ and no packages. The register
helpers (`registers/`) also need Node 22+ and Edge, Chrome or Chromium; they are optional.

Built and tuned for naming software apps. For other products, say so to the user: the App
Store check and the default trademark classes may not fit, and the brief needs adapting.

## Not legal advice
Verdicts are screening results. Say so to the user, and tell them the finalist needs a trademark
professional. Never report "nothing found" for a check that did not actually return results
(an empty page, a blocked site, a failed lookup is **incomplete**, not clear).

## Steps

1. **Get the brief.** Everything about the product lives in one JSON file. If the user has none,
   run `python screener.py --init <name>-brief.json` and fill it in *with the user* by asking:
   what the product does and for whom; the markets; competitors and platform names that are off
   limits (`banned_names`); words too crowded in the field (`crowded_roots`); which domains
   matter (`domains.tlds`, `preferred`); which stores (`stores`); which Nice trademark classes
   a clash would hurt (`trademarks.core_classes`; 9 and 42 for software, 35 retail, 25 clothing,
   30 food, 36 finance, 41 entertainment); the languages to check for a bad meaning.
2. **Read the instructions for this brief:** `python brief.py --brief <brief.json>` prints the
   playbook filled in for the product. Follow it. (`--render prompt.md` prints the loop's prompt.)
3. **Candidates.** Take the user's names, or `--generate N` for coined ones, and invent more of your
   own from the brief's themes. Prefer coined or less obvious names: short friendly ones are taken.
4. **Screen:** `python screener.py --brief <brief.json> --names A B C` (or `--generate 30`). It
   checks domains and the App Store and prints a **preliminary** verdict. It skips names already in
   the data folder's `screened.jsonl`.
5. **Research each survivor, one at a time**, with the playbook's steps 3-5: web searches from its
   templates, Google Play, one-letter and same-sound variants, trademark leads, meaning in the
   brief's languages. `registers/README.md` shows how to read the Canadian and WIPO registers
   with a real browser (run its control search first). The USPTO must be searched by hand.
   Stop at the first BLOCKED reason.
6. **Record** a line in `<data folder>/screened.jsonl`: `{"name", "verdict", "deciding_factor",
   "checked_on"}`, with the sources and what was not checked.
7. **Report** to the user: the survivors (CLEAR and PARTIAL) with the one-line reason and the risk
   to weigh, the count of blocked names and why, and what the user must still do (prices at a
   registrar, reserve the name in the store consoles, trademark professional for the finalist).

## Unattended, with a local model
`python loop.py --brief <brief.json>` keeps a local OpenAI-compatible model (LM Studio, Ollama,
llama.cpp) proposing, screening and researching names until Ctrl+C or `--until 08:00`. It reads
no registers, so its CLEAR names are marked `trademarks (official registers)` incomplete; confirm
them yourself. `pip install ddgs` first avoids DuckDuckGo's rate limit.

## Rules that earned their place
- Verdict rules and the similarity test are in the playbook (sections 2-3). Apply the first that matches.
- Check one-letter neighbours and same-sound spellings early.
- Mirror sites (Justia, Trademarkia, uspto.report) are often stale; confirm on the official register.
- A different industry is not automatically safe; a famous brand blocks in any class.
- A 404 from RDAP means unregistered, not cheap: premium names answer 404 too.
- Do not work around a site's bot check. Say the check is incomplete.
- Never print or store anything private from the user's brief beyond its own data folder.
