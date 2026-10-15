import unittest

from scripts.build_safe_wordlist import parse_scowl

SAMPLE = """\
35 [] [12dicts] 40 [3esl]: apple <n>: apples

50 [12dicts] 70 [moby]: apple <v>: apples, appled

40 [3esl] 60 [12dicts] [brif]: A: asshole <n> (vulgar-1): assholes

40 [3esl] 60 [12dicts]: B: colour <n>: colours

35 GB [ukfreq]: lorry <n>: lorries

60 [12dicts] 70 [moby]: - <n>: apple's

50 [name] 70 [moby]: Aachen <n/name?>: Aachen's

70 [5d+2a] [moby]: kettle* <n>: kettles

# a comment line
"""


class ScowlParserTest(unittest.TestCase):
    def setUp(self):
        self.words = parse_scowl(SAMPLE)

    def test_size_is_smallest_noun_entry(self):
        self.assertEqual(self.words["apple"].size, 35)

    def test_american_variant_entries_are_read_with_usage_notes(self):
        self.assertIn("vulgar-1", self.words["asshole"].usage)

    def test_british_only_spellings_and_regions_are_skipped(self):
        self.assertNotIn("colour", self.words)
        self.assertNotIn("lorry", self.words)

    def test_capitalized_and_placeholder_lemmas_are_skipped(self):
        self.assertNotIn("aachen", self.words)
        self.assertNotIn("-", self.words)

    def test_source_tags_of_noun_entries_are_kept(self):
        self.assertEqual(self.words["apple"].tags, {"", "12dicts", "3esl"})

    def test_lemma_annotations_are_stripped(self):
        self.assertEqual(self.words["kettle"].size, 70)


if __name__ == "__main__":
    unittest.main()
