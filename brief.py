"""The brief: everything about *your* product that the name screening needs.

One JSON file (see brief.example.json). Everything the tools used to assume (what the
product is, which names are off limits, which domains and stores to check, which trademark
classes matter) is read from it, so the same scripts serve any product.

    python screener.py --init my-brief.json     # writes a starter to edit

Screening data (what has been checked, full results, model transcripts) is kept beside
the brief, in its own folder, so one checkout can hold any number of projects.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "project": "my-product",
    "product": {
        "kind": "app",
        "description": "Describe what the product does, in two or three sentences.",
        "story": "",
        "markets": "Home market first; where else it is sold.",
        "requirements": [
            "Short, easy to say, easy to spell after hearing it once.",
            "A standard-price domain in the preferred top-level domain.",
            "No live trademark conflict in the product's field.",
        ],
    },
    # Plain-language list of the categories where an exact-name product would block you.
    "related_categories": ["products that do what yours does"],
    # Names that are off limits: competitors, platform owners, anything you must not echo.
    "banned_names": [],
    # Lowercase i + capital (iPhone-style) is the platform owner's; set false if irrelevant.
    "block_i_prefix": False,
    # Word stems so crowded in your field that a name using one is hard to defend.
    "crowded_roots": [],
    "name_length": [4, 9],
    "domains": {"tlds": ["com", "app"], "preferred": "app"},
    "stores": {
        "app_store": True,                 # iTunes Search API
        "countries": ["us"],               # App Store storefronts to ask
        "risky_genres": ["utilities", "productivity", "photo & video", "business",
                         "social networking", "developer tools", "entertainment"],
        "google_play": True,               # searched by the agent, not the script
    },
    "trademarks": {
        "core_classes": [9, 42],           # Nice classes where a clash would block you
        "jurisdictions": ["United States"],
    },
    "languages": ["English"],              # checked for an adverse meaning
    "search_region": "us-en",              # DuckDuckGo region for the agent's searches
    "accept_language": "en-US,en;q=0.9",
    "generator": {
        "roots": ["nov", "lum", "vel", "aris", "tor", "mir", "sol", "kel", "zen", "ora",
                  "pel", "dur", "fen", "tal", "wyn"],
        "endings": ["o", "a", "io", "ly", "ra", "en", "ix", "elo", "ari", "uno"],
        "themes": [],                      # prose hints for the model, e.g. "spare capacity: aux, extra"
    },
}

# RDAP servers by TLD. Anything else goes through rdap.org, which redirects to the right one.
RDAP = {
    "com": "https://rdap.verisign.com/com/v1/domain/{}",
    "net": "https://rdap.verisign.com/net/v1/domain/{}",
    "app": "https://pubapi.registry.google/rdap/domain/{}",
    "dev": "https://pubapi.registry.google/rdap/domain/{}",
    "ca": "https://rdap.ca.fury.ca/rdap/domain/{}",
}
RDAP_FALLBACK = "https://rdap.org/domain/{}"

NICE = {
    9: "downloadable software, apps, cameras, microphones, computer peripherals, recording and transmitting apparatus",
    35: "advertising, business management, online marketplaces",
    36: "finance, insurance, payments, crypto",
    38: "telecommunications: transmitting audio, video and data, conferencing, streaming",
    41: "entertainment, education, publishing",
    42: "software as a service, software design and development, hosting, IT services",
    45: "legal and security services, social networking services",
}


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load(path):
    """The brief at `path`, over the defaults, checked."""
    with open(path, encoding="utf-8") as f:
        brief = _merge(DEFAULTS, json.load(f))
    d = brief["domains"]
    if d["preferred"] not in d["tlds"]:
        raise ValueError(f"domains.preferred ({d['preferred']!r}) must be one of domains.tlds")
    lo, hi = brief["name_length"]
    if not 1 <= lo <= hi:
        raise ValueError("name_length must be [shortest, longest]")
    brief["_path"] = os.path.abspath(path)
    brief["banned_names"] = [n.lower() for n in brief["banned_names"]]
    return brief


def data_dir(brief, override=None):
    """Where this project's screening data lives: beside the brief unless told otherwise."""
    d = override or os.path.join(os.path.dirname(brief["_path"]),
                                 re.sub(r"[^A-Za-z0-9_.-]+", "-", brief["project"]) + "-data")
    os.makedirs(d, exist_ok=True)
    return d


def init(path):
    """Writes the example brief to `path` for the user to edit; never overwrites."""
    if os.path.exists(path):
        raise FileExistsError(path)
    with open(os.path.join(HERE, "brief.example.json"), encoding="utf-8") as f:
        text = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _bullets(items, empty="none"):
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


def _classes(numbers):
    return ", ".join(str(n) for n in numbers[:-1]) + (" or " if len(numbers) > 1 else "") + str(numbers[-1])


def render(template, brief):
    """The playbook / prompt template with the brief filled in."""
    p, tm = brief["product"], brief["trademarks"]
    rows = "\n".join(
        f"| **{n}** | {NICE.get(n, 'see the Nice classification')} | Core class for this product. |"
        for n in tm["core_classes"])
    values = {
        "KIND": p["kind"],
        "DESCRIPTION": p["description"],
        "STORY": p["story"] or "(none given)",
        "MARKETS": p["markets"],
        "REQUIREMENTS": _bullets(p["requirements"]),
        "CATEGORIES": "; ".join(brief["related_categories"]),
        "BANNED": ", ".join(brief["banned_names"]) or "(none listed)",
        "CROWDED": ", ".join(brief["crowded_roots"]) or "(none listed)",
        "CLASSES": _classes(tm["core_classes"]),
        "CLASS_ROWS": rows,
        "JURISDICTIONS": ", ".join(tm["jurisdictions"]),
        "LANGUAGES": ", ".join(brief["languages"]),
        "TLDS": ", ".join("." + t for t in brief["domains"]["tlds"]),
        "PREFERRED": "." + brief["domains"]["preferred"],
        "LENGTH": f"{brief['name_length'][0]}-{brief['name_length'][1]}",
        "THEMES": _bullets(brief["generator"]["themes"], "any: coined blends and short real-word echoes"),
        "STORES": ("the Apple App Store and Google Play" if brief["stores"]["app_store"]
                   and brief["stores"]["google_play"] else
                   "the Apple App Store" if brief["stores"]["app_store"] else
                   "Google Play" if brief["stores"]["google_play"] else "app stores (not used here)"),
    }
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values[m.group(1)], template)


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Print playbook.md or prompt.md filled in from a brief.")
    ap.add_argument("--brief", required=True)
    ap.add_argument("--render", default="playbook.md", choices=["playbook.md", "prompt.md"])
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    with open(os.path.join(HERE, args.render), encoding="utf-8") as f:
        print(render(f.read(), load(args.brief)))
