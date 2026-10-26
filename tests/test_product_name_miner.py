"""Offline tests: nothing here touches the network.   python -m unittest discover -s tests"""
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import brief as briefmod  # noqa: E402
import screener as sc  # noqa: E402

EXAMPLE = os.path.join(ROOT, "brief.example.json")


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class BriefTests(unittest.TestCase):
    def test_example_loads_and_fills_defaults(self):
        b = briefmod.load(EXAMPLE)
        self.assertEqual(b["domains"]["preferred"], "app")
        self.assertIn("mint", b["banned_names"])
        self.assertIn("generator", b)

    def test_partial_brief_gets_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json")
            write_json(p, {"project": "x", "stores": {"countries": ["gb"]}})
            b = briefmod.load(p)
            self.assertEqual(b["stores"]["countries"], ["gb"])
            self.assertTrue(b["stores"]["app_store"])        # kept from the defaults

    def test_preferred_domain_must_be_checked(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json")
            write_json(p, {"domains": {"tlds": ["com"], "preferred": "app"}})
            with self.assertRaises(ValueError):
                briefmod.load(p)

    def test_init_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mine.json")
            briefmod.init(p)
            briefmod.load(p)
            with self.assertRaises(FileExistsError):
                briefmod.init(p)

    def test_templates_render_with_no_placeholder_left(self):
        b = briefmod.load(EXAMPLE)
        for name in ("playbook.md", "prompt.md"):
            self.assertNotRegex(briefmod.render(read(name), b), r"\{\{[A-Z_]+\}\}", name)
        playbook = briefmod.render(read("playbook.md"), b)
        self.assertIn("9, 36 or 42", playbook)
        self.assertIn("personal finance", playbook)
        self.assertRegex(playbook, r"(?m)^## 7\.")           # the loop reads sections 1 and 7

    def test_every_template_key_is_provided(self):
        b = briefmod.load(EXAMPLE)
        keys = set()
        for name in ("playbook.md", "prompt.md"):
            keys |= set(re.findall(r"\{\{([A-Z_]+)\}\}", read(name)))
        briefmod.render("".join("{{%s}}" % k for k in keys), b)   # a KeyError would fail here


class ScreenerTests(unittest.TestCase):
    def setUp(self):
        self.b = briefmod.load(EXAMPLE)

    def test_title_matches_whole_words_only(self):
        self.assertTrue(sc.title_matches("Tellaro", "Tellaro: Budget Planner"))
        self.assertTrue(sc.title_matches("Tellaro", "tellaro"))
        self.assertFalse(sc.title_matches("Pan", "Pandora"))

    def test_variants(self):
        v = sc.variants("Quorvel")
        self.assertIn("quovrel", v)                            # transposition
        self.assertIn("quorel", v)                             # one letter dropped
        self.assertNotIn("quorvel", v)

    def test_prefilter(self):
        self.assertEqual(sc.prefilter("Mint", self.b)[0], "BLOCKED")
        self.assertEqual(sc.prefilter("Taxly", self.b), (None, ["crowded root"]))
        self.assertIn("length outside 4-9", sc.prefilter("Abcdefghijkl", self.b)[1])
        self.b["block_i_prefix"] = True
        self.assertEqual(sc.prefilter("iThing", self.b)[0], "BLOCKED")

    def test_generate_respects_the_brief(self):
        names = sc.generate(50, self.b, seed=1)
        lo, hi = self.b["name_length"]
        self.assertTrue(names)
        for n in names:
            self.assertTrue(lo <= len(n) <= hi, n)
            self.assertFalse(any(r in n.lower() for r in self.b["crowded_roots"]), n)
        self.assertEqual(names, sc.generate(50, self.b, seed=1))   # repeatable

    def test_preliminary_verdicts(self):
        pre = lambda *a: sc.preliminary(*a, self.b)           # noqa: E731
        self.assertEqual(pre("BLOCKED", {}, [], ["x"], [])[0], "BLOCKED")
        hit = [{"title": "Foo", "seller": "S", "genre": "Finance"}]
        self.assertEqual(pre(None, {}, hit, [], [])[0], "BLOCKED")
        other = [{"title": "Foo", "seller": "S", "genre": "Games"}]
        self.assertEqual(pre(None, {}, other, [], [])[0], "PARTIAL")
        self.assertEqual(pre(None, {"app": "registered"}, [], [], [])[0], "PARTIAL")
        self.assertEqual(pre(None, {"app": "not_registered"}, [], [], [])[0], "NEEDS_TM_REVIEW")
        self.assertIn("not checked", pre(None, {}, [], [], ["domains"])[1])

    def test_offline_row_never_claims_a_check_it_did_not_make(self):
        row = sc.screen("Tellaro", self.b, offline=True)
        self.assertEqual(row["domain_app"], "not_checked")
        self.assertIn("domains", row["checks_incomplete"])
        self.assertIn("trademarks", row["checks_incomplete"])
        self.assertEqual(row["verdict"], "NEEDS_TM_REVIEW")
        for tld in self.b["domains"]["tlds"]:
            self.assertIn(f"domain_{tld}", row)

    def test_known_names_skip_but_incomplete_ones_do_not(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.jsonl")
            with open(p, "w") as f:
                f.write(json.dumps({"name": "Done", "verdict": "CLEAR"}) + "\n")
                f.write(json.dumps({"name": "Retry", "verdict": "INCOMPLETE"}) + "\n")
            self.assertEqual(sc.load_known([p, os.path.join(d, "missing.jsonl")]), {"done"})


class LoopTests(unittest.TestCase):
    def test_loop_imports_and_uses_the_brief(self):
        import loop
        loop.BRIEF = briefmod.load(EXAMPLE)
        row = sc.screen("Tellaro", loop.BRIEF, offline=True)
        task = loop.task(row)
        self.assertIn(".com not_checked, .app not_checked, .ca not_checked", task)   # the brief's TLDs, in order
        self.assertIn("(US, CA)", task)                                              # its storefronts
        self.b2 = dict(loop.BRIEF, domains={"tlds": ["io"], "preferred": "io"}, stores=dict(loop.BRIEF["stores"], app_store=False))
        loop.BRIEF = self.b2
        other = loop.task(sc.screen("Tellaro", self.b2, offline=True))
        self.assertIn(".io not_checked", other)
        self.assertNotIn(".com", other)
        self.assertNotIn("App Store", other)


if __name__ == "__main__":
    unittest.main()
