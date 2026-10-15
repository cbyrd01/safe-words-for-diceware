import unittest

from scripts import safe_wordlist_rules as rules
from scripts.safe_wordlist_rules import CategoryRule, Overrides, Sense


def sense(synset, pos="n", lexname="noun.artifact", ancestors=(), count=0, definition="",
          usage=(), instance=False, proper=False):
    return Sense(
        synset=synset,
        pos=pos,
        lexname=lexname,
        count=count,
        is_instance=instance,
        is_proper=proper,
        usage_domains=frozenset(usage),
        ancestors=frozenset((synset,) + tuple(ancestors)),
        definition=definition,
    )


CATEGORIES = {
    "animal.n.01": CategoryRule("animal.n.01", True, "animals", 4),
    "ungulate.n.01": CategoryRule("ungulate.n.01", False, "hoofed mammals", 9),
    "device.n.01": CategoryRule("device.n.01", True, "devices", 6),
}
NO_OVERRIDES = Overrides()


def evaluate(word, senses, overrides=NO_OVERRIDES, verb_base=None):
    return [r.rule for r in rules.evaluate_word(word, senses, CATEGORIES, overrides, verb_base)]


class CategoryGateTest(unittest.TestCase):
    def test_accepts_noun_in_allowed_category(self):
        self.assertEqual(evaluate("otter", [sense("otter.n.01", lexname="noun.animal", ancestors=("animal.n.01",))]), [])

    def test_rejects_noun_outside_listed_categories(self):
        self.assertEqual(evaluate("idea", [sense("idea.n.01", lexname="noun.cognition")]), ["category"])

    def test_most_specific_category_wins(self):
        goat = sense("goat.n.01", lexname="noun.animal", ancestors=("ungulate.n.01", "animal.n.01"))
        self.assertEqual(evaluate("goat", [goat]), ["category"])

    def test_rejects_words_mostly_used_as_verbs(self):
        senses = [sense("run.n.01", count=1, ancestors=("device.n.01",)), sense("run.v.01", pos="v", count=9)]
        self.assertEqual(evaluate("run", senses), ["pos"])

    def test_dominant_pos_falls_back_to_sense_count_and_prefers_nouns(self):
        senses = [sense("a.n.01"), sense("a.v.01", pos="v")]
        self.assertEqual(rules.dominant_pos(senses), "n")

    def test_main_sense_is_most_frequent_noun_sense(self):
        senses = [sense("x.n.01", count=1), sense("x.n.02", count=5)]
        self.assertEqual(rules.primary_noun_sense(senses).synset, "x.n.02")


class HardDenialTest(unittest.TestCase):
    def test_any_person_sense_rejects(self):
        senses = [
            sense("fox.n.01", lexname="noun.animal", ancestors=("animal.n.01",)),
            sense("fox.n.03", lexname="noun.person"),
        ]
        self.assertIn("denied-category", evaluate("fox", senses))

    def test_offensive_usage_label_on_any_sense_rejects(self):
        senses = [
            sense("can.n.01", ancestors=("device.n.01",)),
            sense("buttocks.n.01", lexname="noun.substance", usage=("obscenity.n.02",)),
        ]
        self.assertIn("usage-label", evaluate("can", senses))

    def test_weapon_only_rejects_as_main_sense(self):
        tank = [
            sense("tank.n.02", count=5, ancestors=("device.n.01",)),
            sense("tank.n.01", count=1, ancestors=("weapon.n.01", "device.n.01")),
        ]
        self.assertEqual(evaluate("tank", tank), [])
        gun = [sense("gun.n.01", ancestors=("weapon.n.01", "device.n.01"))]
        self.assertIn("denied-primary-hypernym", evaluate("gun", gun))

    def test_high_risk_definition_on_any_sense_rejects(self):
        senses = [
            sense("cherry.n.01", ancestors=("device.n.01",)),
            sense("cherry.n.09", lexname="noun.state", definition="slang for sexual inexperience"),
        ]
        self.assertIn("denied-gloss", evaluate("cherry", senses))

    def test_gendered_main_sense_rejects(self):
        rooster = [sense("rooster.n.01", lexname="noun.animal", ancestors=("animal.n.01",),
                         definition="adult male chicken")]
        self.assertEqual(evaluate("rooster", rooster), ["gendered"])

    def test_instance_senses_do_not_decide_category_but_countries_reject(self):
        senses = [
            sense("turkey.n.02", lexname="noun.animal", ancestors=("animal.n.01",)),
            sense("turkey.n.01", lexname="noun.location", instance=True, proper=True, ancestors=("country.n.02",)),
        ]
        self.assertEqual(evaluate("turkey", senses), ["proper-name"])

    def test_proper_only_words_are_not_common_nouns(self):
        senses = [sense("dna.n.01", lexname="noun.substance", proper=True)]
        self.assertEqual(evaluate("dna", senses), ["not-in-wordnet"])

    def test_verb_forms_need_attested_noun_use(self):
        tore = [sense("torus.n.01", lexname="noun.shape", ancestors=("device.n.01",))]
        self.assertEqual(evaluate("tore", tore, verb_base="tear"), ["verb-form"])
        stove = [sense("stove.n.01", count=6, ancestors=("device.n.01",))]
        self.assertEqual(evaluate("stove", stove, verb_base="stave"), [])
        beads = [sense("bead.n.01", ancestors=("device.n.01",))]
        self.assertEqual(evaluate("beads", beads, verb_base="bead"), [])

    def test_waivers_skip_soft_rules_but_never_the_manual_denylist(self):
        water = [
            sense("water.n.01", lexname="noun.substance", ancestors=("device.n.01",)),
            sense("urine.n.01", lexname="noun.substance", usage=("obscenity.n.02",)),
        ]
        waived = Overrides(waivers={"water": frozenset({"usage-label"})})
        self.assertEqual(evaluate("water", water, waived), [])
        both = Overrides(denylist={"water": "test"}, waivers={"water": frozenset({"usage-label", "manual-denylist"})})
        self.assertEqual(evaluate("water", water, both), ["manual-denylist"])

    def test_form_rule(self):
        senses = [sense("ox.n.01", lexname="noun.animal", ancestors=("animal.n.01",))]
        self.assertEqual(evaluate("ox", senses), ["form"])


class DuplicateTest(unittest.TestCase):
    @staticmethod
    def keep_first_alphabetically(word, shared):
        return (word,)

    def test_close_spelling_variant_is_dropped(self):
        synsets = {"raccoon": frozenset({"raccoon.n.02"}), "racoon": frozenset({"raccoon.n.02"})}
        dropped = rules.find_duplicates(synsets, synsets, self.keep_first_alphabetically)
        self.assertEqual(dropped, {"racoon": "raccoon"})

    def test_sharing_one_sense_is_not_enough(self):
        synsets = {"house": frozenset({"house.n.01", "home.n.01"}), "home": frozenset({"home.n.01", "home.n.02"})}
        self.assertEqual(rules.find_duplicates(synsets, synsets, self.keep_first_alphabetically), {})

    def test_plural_dropped_when_singular_present(self):
        self.assertEqual(rules.find_plural_pairs(["stair", "stairs", "grits", "glass"]), {"stairs": "stair"})

    def test_variant_chains_do_not_spread(self):
        synsets = {
            "hammock": frozenset({"hammock.n.01", "hummock.n.01"}),
            "hummock": frozenset({"hummock.n.01"}),
            "knoll": frozenset({"hummock.n.01"}),
        }

        def prefer(word, shared):
            return ({"hammock": 0, "knoll": 1, "hummock": 2}[word],)

        dropped = rules.find_duplicates(synsets, synsets, prefer)
        self.assertNotIn("hammock", dropped)
        self.assertEqual(dropped["hummock"], "hammock")


class CombinationTest(unittest.TestCase):
    def test_phrase_tokens_match_after_plural_stripping(self):
        conflicts = rules.find_phrase_conflicts(["brown", "shower", "lake"], [(("brown", "showers"), "list")])
        self.assertEqual([c.words for c in conflicts], [("brown", "shower")])

    def test_phrase_needs_every_token(self):
        self.assertEqual(rules.find_phrase_conflicts(["golden"], [(("golden", "shower"), "list")]), [])

    def test_closed_compound_splits_into_two_words(self):
        conflicts = rules.find_compound_conflicts(["pot", "head", "lake"], [("potheads", "list")])
        self.assertEqual([c.words for c in conflicts], [("pot", "head")])

    def test_boundary_term_spanning_the_join(self):
        conflicts = rules.find_boundary_conflicts(["zebra", "pear", "grape"], ["rape"])
        self.assertEqual([c.words for c in conflicts], [("zebra", "pear")])

    def test_resolution_drops_the_word_in_most_conflicts(self):
        conflicts = [
            rules.Conflict(("a", "hub"), "phrase", ""),
            rules.Conflict(("b", "hub"), "phrase", ""),
            rules.Conflict(("c", "d"), "phrase", ""),
        ]
        dropped = rules.resolve_conflicts(conflicts, lambda word: (word,))
        self.assertIn("hub", dropped)
        self.assertEqual(len(dropped), 2)

    def test_compound_naming_a_person_is_unsafe(self):
        couch_potato = [sense("couch_potato.n.01", lexname="noun.person")]
        self.assertIsNotNone(rules.unsafe_compound_reason(couch_potato))

    def test_body_compound_needs_a_usage_label(self):
        air_cell = [sense("alveolus.n.01", lexname="noun.body")]
        self.assertIsNone(rules.unsafe_compound_reason(air_cell))
        bay_window = [sense("pot.n.07", lexname="noun.body", usage=("colloquialism.n.01",))]
        self.assertIsNotNone(rules.unsafe_compound_reason(bay_window))


class HelpersTest(unittest.TestCase):
    def test_stem_word(self):
        self.assertEqual(rules.stem_word("berries"), "berry")
        self.assertEqual(rules.stem_word("cats"), "cat")
        self.assertEqual(rules.stem_word("glass"), "glass")
        self.assertEqual(rules.stem_word("bus"), "bus")

    def test_dice_list(self):
        words = [f"w{i:04d}" for i in range(1296)][::-1]
        lines = rules.format_dice_list(words, 4)
        self.assertEqual(lines[0], "1111\tw0000")
        self.assertEqual(lines[-1], "6666\tw1295")
        with self.assertRaises(ValueError):
            rules.format_dice_list(words[:-1], 4)

    def test_match_category_prefers_deny_on_equal_depth(self):
        cats = {"a.n.01": CategoryRule("a.n.01", True, "a", 5), "b.n.01": CategoryRule("b.n.01", False, "b", 5)}
        rule = rules.match_category(sense("x.n.01", ancestors=("a.n.01", "b.n.01")), cats)
        self.assertFalse(rule.allow)


if __name__ == "__main__":
    unittest.main()
