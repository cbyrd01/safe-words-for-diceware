import unittest

from scripts.download_and_consolidate_wordlists import (
    parse_words,
    stem_word,
    unique_after_stemming,
)


class ConsolidationHelpersTest(unittest.TestCase):
    def test_parse_words_eff_tab(self) -> None:
        content = "11111\tApple\n22222\tBerries\n"
        self.assertEqual(parse_words(content, "eff_tab"), ["apple", "berries"])

    def test_parse_words_plain(self) -> None:
        content = "Alpha\nBeta\n"
        self.assertEqual(parse_words(content, "plain"), ["alpha", "beta"])

    def test_parse_words_unknown_parser_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_words("value\n", "unknown")

    def test_stem_word_plural_reduction(self) -> None:
        self.assertEqual(stem_word("berries"), "berry")
        self.assertEqual(stem_word("cats"), "cat")
        self.assertEqual(stem_word("glass"), "glass")

    def test_unique_after_stemming_uses_representative_word(self) -> None:
        stem_map = unique_after_stemming(["berries", "berry", "cats", "cat"])
        self.assertEqual(stem_map["berry"], "berries")
        self.assertEqual(stem_map["cat"], "cat")


if __name__ == "__main__":
    unittest.main()
