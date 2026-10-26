# Reading the trademark registers from a script

Two official registers can be read with a real browser (headless Edge, Chrome or Chromium, driven over its
DevTools port; Node 22 or later and Python, nothing to install; BROWSER_EXE names the browser if needed). Bash scripts; on Windows use Git Bash.

    ./cipo.sh "examp*"                  # Canadian Trademarks Database (CIPO): results text
    ./wipo.sh example Embedded           # WIPO Global Brand Database: contains the term
    ./wipo.sh example Phonetic           # ... sounds like it (also Fuzzy, Stemming)
    node render.mjs URL 8               # any page's visible text after its scripts ran

- **CIPO** takes `*` wildcards (`exam*`, `*xari`). Its classes and owners are on each
  record page: `https://ised-isde.canada.ca/cipo/trademark-search/<application number>?lang=eng`.
- **WIPO** covers 89 sources, including the U.S., the EU, the U.K. and Canada. It lists
  the 30 most relevant results of the mode chosen.
- **Always run a control first**: a mark you know exists (`lenovo` gives 100+ hits on both).
  A search that fails to run says "no results", which proves nothing. The USPTO's own
  search page does this through a URL, and it blocks this browser with a 403 after a few
  requests: search the USPTO by hand (tmsearch.uspto.gov).
- Some sites (Justia, Trademarkia) put up a bot check. Do not work around it.
- Written 2026-10-23 against the sites as they were; if a layout changes, the controls
  fail first.
