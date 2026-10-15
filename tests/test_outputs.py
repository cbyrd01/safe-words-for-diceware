"""Invariants of the committed wordlists, reports and filter files.

These need NLTK (for its stemmer) but no network access or WordNet; rebuilding with
scripts/build_safe_wordlist.py must keep them true.
"""

import csv
import itertools
import json
import re
import unittest
from pathlib import Path

from nltk.stem import SnowballStemmer

from scripts import safe_wordlist_rules as rules

REPO = Path(__file__).resolve().parent.parent


def entries(path):
    out = []
    for line in (REPO / path).read_text(encoding="utf-8").splitlines():
        body = line.split("#", 1)[0].strip()
        if body:
            out.append(body)
    return out


class OutputInvariantsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safe = (REPO / "wordlists/safe-words.txt").read_text(encoding="utf-8").split("\n")[:-1]
        cls.dice = [line.split("\t") for line in (REPO / "wordlists/safe-diceware-1296.txt").read_text(encoding="utf-8").splitlines()]
        with (REPO / "review/word-decisions.tsv").open(encoding="utf-8") as handle:
            cls.decisions = list(csv.DictReader(handle, delimiter="\t"))
        cls.stats = json.loads((REPO / "review/stats.json").read_text(encoding="utf-8"))

    def test_safe_list_is_sorted_unique_and_well_formed(self):
        self.assertEqual(self.safe, sorted(set(self.safe)))
        for word in self.safe:
            self.assertRegex(word, rf"^[a-z]{{{rules.MIN_WORD_LENGTH},{rules.MAX_WORD_LENGTH}}}$")

    def test_dice_list_has_every_code_once_with_safe_words(self):
        self.assertEqual([code for code, _ in self.dice], rules.dice_codes(4))
        words = [word for _, word in self.dice]
        self.assertEqual(words, sorted(set(words)))
        self.assertLessEqual(set(words), set(self.safe))

    def test_decision_report_matches_safe_list(self):
        accepted = sorted(row["word"] for row in self.decisions if row["decision"] == "accepted")
        self.assertEqual(accepted, self.safe)
        for row in self.decisions:
            self.assertEqual(row["decision"] == "excluded", bool(row["rules"]), row["word"])

    def test_stats_match_files(self):
        self.assertEqual(self.stats["safe_words"], len(self.safe))
        self.assertEqual(self.stats["candidates"], len(self.decisions))
        self.assertEqual(self.stats["dice_list_words"], len(self.dice))

    def test_no_denylisted_word_is_published(self):
        denied = {line.split()[0] for line in entries("filters/denylist.txt")}
        self.assertFalse(denied & set(self.safe))

    def test_filter_entries_name_real_candidates(self):
        candidates = {row["word"] for row in self.decisions}
        for path in ("filters/denylist.txt", "filters/rule-waivers.txt"):
            for line in entries(path):
                self.assertIn(line.split()[0], candidates, f"{path}: {line}")

    def test_no_phrase_denylist_pair_is_reachable(self):
        stem = SnowballStemmer("english").stem
        safe = {stem(word) for word in self.safe}
        for line in entries("filters/phrase-denylist.txt"):
            tokens = [stem(t) for t in line.split()]
            self.assertFalse(all(t in safe for t in tokens), line)

    def test_no_two_safe_words_share_a_stem(self):
        stem = SnowballStemmer("english").stem
        by_stem = {}
        for word in self.safe:
            by_stem.setdefault(stem(word), []).append(word)
        self.assertEqual([group for group in by_stem.values() if len(group) > 1], [])


class FilterFileFormatTest(unittest.TestCase):
    def test_categories_lines(self):
        for line in entries("filters/categories.txt"):
            self.assertRegex(line, r"^(allow|deny)\s+[a-z0-9_.'-]+\.n\.\d\d$")

    def test_rule_waivers_only_waive_soft_rules(self):
        waivable = {"pos", "category", "denied-category", "denied-hypernym", "denied-gloss",
                    "denied-primary-hypernym", "denied-primary-gloss", "usage-label", "verb-form",
                    "proper-name", "gendered", "unfamiliar"}
        for line in entries("filters/rule-waivers.txt"):
            word, ids = line.split()
            self.assertLessEqual(set(ids.split(",")), waivable, line)

    def test_denylist_has_no_duplicates(self):
        words = [line.split()[0] for line in entries("filters/denylist.txt")]
        duplicates = [w for w, group in itertools.groupby(sorted(words)) if len(list(group)) > 1]
        self.assertEqual(duplicates, [])


if __name__ == "__main__":
    unittest.main()
