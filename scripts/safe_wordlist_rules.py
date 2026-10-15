"""Selection rules for the safe Diceware wordlist.

This module is pure logic: it works on plain ``Sense`` records so it can be
unit-tested without WordNet installed. ``build_safe_wordlist.py`` adapts
WordNet (via NLTK) into these records and handles all I/O.

The model has three layers, applied in order:

1. **Positive model** - a word is only eligible when WordNet says it is
   predominantly a noun whose main sense is in a concrete, low-risk lexical
   category (animals, plants, food, artifacts, natural objects, ...).
   Verbs and adverbs are never eligible; adjectives only via a curated
   allowlist.
2. **Hard denials** - a word is rejected if *any* of its senses is in a
   category that can describe people or bodies, is labelled obscene / slur /
   disparaging, or matches high-risk topics (sex, drugs, violence, ...).
   Some lower-risk topics (weapons, religion, prisons) only reject a word
   when they are its *main* noun sense.
3. **Combination screening** - pairs of accepted words that form a known
   problematic phrase or compound are resolved by dropping one word.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional, Sequence


WORD_PATTERN = re.compile(r"^[a-z]+$")
MIN_WORD_LENGTH = 3
MAX_WORD_LENGTH = 9

# --- Positive model ---------------------------------------------------------

# WordNet lexicographer files ("lexnames") whose members are concrete and
# rarely combine into something about people.
ALLOWED_NOUN_CATEGORIES = frozenset(
    {
        "noun.animal",
        "noun.artifact",
        "noun.food",
        "noun.location",
        "noun.object",
        "noun.phenomenon",
        "noun.plant",
        "noun.shape",
        "noun.substance",
        "noun.time",
    }
)

# A word with ANY common-noun sense in these categories is rejected: such words
# can describe a person or a body, which is where most "BIG + SISTER" style
# combinations get their meaning.
DENIED_NOUN_CATEGORIES = frozenset(
    {
        "noun.body",
        "noun.feeling",
        "noun.motive",
        "noun.person",
    }
)

# WordNet usage labels that mark a sense as offensive.
DENIED_USAGE_DOMAINS = frozenset(
    {
        "disparagement.n.01",
        "ethnic_slur.n.01",
        "obscenity.n.02",
        "street_name.n.02",  # drug slang
        "trademark.n.02",  # brand names ("colt" is also a revolver)
    }
)

# Hypernyms that reject a word when ANY sense descends from them.
DENIED_ANCESTORS_ANY_SENSE = frozenset(
    {
        "alcohol.n.01",
        "body_waste.n.01",
        "brothel.n.01",
        "cigar.n.01",
        "cigarette.n.01",
        "coffin.n.01",
        "contraceptive.n.01",
        "drug_of_abuse.n.01",
        "grave.n.02",
        "hallucinogen.n.01",
        "instrument_of_execution.n.01",
        "instrument_of_punishment.n.01",
        "narcotic.n.01",
        "psychoactive_drug.n.01",
        "sanitary_napkin.n.01",
        "sex_toy.n.01",
        "tampon.n.01",
        "tobacco.n.01",
        "undergarment.n.01",
    }
)

# Hypernyms that reject a word only when its MAIN noun sense descends from
# them ("tank" is fine because its main sense is a container).
DENIED_ANCESTORS_PRIMARY_SENSE = frozenset(
    {
        "ammunition.n.01",
        "calamity.n.01",
        "cemetery.n.01",
        "correctional_institution.n.01",
        "drug.n.01",
        "explosive.n.01",
        "explosive_device.n.01",
        "holy_day.n.01",
        "military_installation.n.01",
        "military_vehicle.n.01",
        "place_of_worship.n.01",
        "poison.n.01",
        "religious_ceremony.n.01",
        "sacred_text.n.01",
        "toilet.n.01",
        "toilet.n.02",
        "toxin.n.01",
        "warship.n.01",
        "weapon.n.01",
    }
)

# Country names ('chile', 'panama') invite combinations about nations.
COUNTRY_ANCESTOR = "country.n.02"

# Definition keywords that reject a word when found in ANY sense's gloss.
DENIED_GLOSS_ANY_SENSE = re.compile(
    r"\b("
    r"sex|sexual\w*|sexually|intercourse|copulat\w*|fornicat\w*|erotic\w*|"
    r"genital\w*|penis|vagina\w*|vulva|testicles?|testes|scrotum|clitoris|"
    r"nipples?|buttocks|anus|orgasm\w*|pornograph\w*|prostitut\w*|"
    r"masturbat\w*|ejaculat\w*|semen|lewd\w*|obscen\w*|vulgar\w*|"
    r"fece?s|faeces|excrement|defecat\w*|urinat\w*|urine|vomit\w*|"
    r"offensive|derogatory|disparag\w*|contemptuous\w*|slur|insult\w*|"
    r"racis\w*|nazi\w*|slave\w*|slavery|lynch\w*|"
    r"murder\w*|massacre\w*|genocide|suicide|tortur\w*|corpse\w*|cadaver\w*|"
    r"dead body|funeral\w*|burial|cremat\w*|"
    r"narcotic\w*|intoxicat\w*|hallucinogen\w*|marijuana|cocaine|heroin|opium"
    r")\b",
    re.IGNORECASE,
)

# Definition keywords that reject a word only when found in its MAIN noun
# sense's gloss.
DENIED_GLOSS_PRIMARY_SENSE = re.compile(
    r"\b("
    r"religio\w*|worship\w*|deity|deities|god|gods|goddess|christian\w*|"
    r"church|islam\w*|muslim\w*|jewish|judaism|hindu\w*|buddhis\w*|sacred|"
    r"holy|weapon\w*|firearm\w*|explosive\w*|kill\w*|prison\w*|jail\w*|"
    r"disease\w*|infection\w*|poison\w*|toxic\w*|alcoholic|liquor|"
    r"gambling|military|warfare"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Sense:
    """One WordNet sense of a word, reduced to what the rules need."""

    synset: str
    pos: str  # "n", "v", "a" (adjective, incl. satellites) or "r"
    lexname: str
    count: int = 0  # tagged corpus frequency of this word in this sense
    is_instance: bool = False  # names a specific person/place/thing
    is_proper: bool = False  # WordNet capitalizes the lemma ("Argentine")
    usage_domains: frozenset = field(default_factory=frozenset)
    ancestors: frozenset = field(default_factory=frozenset)  # incl. itself
    definition: str = ""


@dataclass(frozen=True)
class Reason:
    rule: str
    detail: str


@dataclass(frozen=True)
class Overrides:
    """Human-reviewed exceptions loaded from the ``filters/`` directory."""

    denylist: Mapping[str, str] = field(default_factory=dict)
    allowed_adjectives: frozenset = field(default_factory=frozenset)
    # word -> rule ids that are waived for that word
    waivers: Mapping[str, frozenset] = field(default_factory=dict)


def common_senses(senses: Iterable[Sense]) -> list[Sense]:
    """Drop instance senses (e.g. 'Rice' the playwright, 'Turkey' the country).

    Those describe specific named entities rather than what the lowercase
    word means in a passphrase, so they do not count towards POS/category.
    """
    return [sense for sense in senses if not sense.is_instance]


def dominant_pos(senses: Sequence[Sense]) -> Optional[str]:
    """Return the part of speech the word is mostly used as.

    Uses tagged corpus counts when WordNet has any for the word, otherwise
    the number of senses. Ties go to nouns.
    """
    if not senses:
        return None
    totals: dict[str, int] = {}
    use_counts = any(sense.count for sense in senses)
    for sense in senses:
        totals[sense.pos] = totals.get(sense.pos, 0) + (sense.count if use_counts else 1)
    return max(totals, key=lambda pos: (totals[pos], pos == "n"))


def primary_noun_sense(senses: Sequence[Sense]) -> Optional[Sense]:
    """Most frequent noun sense (WordNet order breaks ties)."""
    nouns = [sense for sense in senses if sense.pos == "n"]
    if not nouns:
        return None
    return max(nouns, key=lambda sense: sense.count) if any(s.count for s in nouns) else nouns[0]


def evaluate_word(
    word: str,
    senses: Sequence[Sense],
    overrides: Overrides,
    verb_base: Optional[str] = None,
) -> list[Reason]:
    """Return every rule the word fails. An empty list means accepted.

    ``verb_base`` is the verb the word inflects, if any ('shook' -> 'shake',
    'seizing' -> 'seize').
    """
    reasons: list[Reason] = []

    def fail(rule: str, detail: str) -> None:
        if rule not in overrides.waivers.get(word, frozenset()):
            reasons.append(Reason(rule, detail))

    if not WORD_PATTERN.match(word) or not MIN_WORD_LENGTH <= len(word) <= MAX_WORD_LENGTH:
        reasons.append(
            Reason("form", f"must be {MIN_WORD_LENGTH}-{MAX_WORD_LENGTH} letters a-z")
        )

    if word in overrides.denylist:
        reasons.append(Reason("manual-denylist", overrides.denylist[word]))

    # A verb form ('tore', 'seizing') reads as a verb even when WordNet also
    # lists a rare noun for it. Keep it only when the noun use is attested in
    # the tagged corpus ('building', 'stove'); plurals ('beads') never count.
    if verb_base and verb_base != word and not word.endswith("s"):
        noun_uses = sum(s.count for s in senses if s.pos == "n" and not s.is_instance)
        if noun_uses == 0:
            fail("verb-form", f"form of the verb '{verb_base}' with no attested noun use")

    for sense in senses:
        if sense.is_instance and COUNTRY_ANCESTOR in sense.ancestors:
            fail("proper-name", f"{sense.synset} is a country")
        elif sense.pos == "a" and sense.is_proper:
            fail("proper-name", f"{sense.synset} is a nationality/proper adjective")

    common = common_senses(senses)
    if not common:
        reasons.append(Reason("not-in-wordnet", "no common-word WordNet entry to verify"))
        return reasons

    # 1. Positive model
    pos = dominant_pos(common)
    primary = primary_noun_sense(common)
    if word in overrides.allowed_adjectives:
        if pos not in {"a", "n"}:
            fail("pos", f"allowlisted adjective but mostly used as '{pos}'")
    elif pos != "n":
        fail("pos", f"mostly used as {_POS_NAMES.get(pos, pos)}, not a noun")
    elif primary is not None and primary.lexname not in ALLOWED_NOUN_CATEGORIES:
        fail(
            "category",
            f"main sense {primary.synset} is {primary.lexname} (not a concrete category)",
        )

    # 2. Hard denials over all common senses
    for sense in common:
        if sense.pos == "n" and sense.lexname in DENIED_NOUN_CATEGORIES:
            fail("denied-category", f"{sense.synset} is {sense.lexname}")
        flagged_usage = sense.usage_domains & DENIED_USAGE_DOMAINS
        if flagged_usage:
            fail("usage-label", f"{sense.synset} labelled {', '.join(sorted(flagged_usage))}")
        flagged_ancestors = sense.ancestors & DENIED_ANCESTORS_ANY_SENSE
        if flagged_ancestors:
            fail("denied-hypernym", f"{sense.synset} is a {', '.join(sorted(flagged_ancestors))}")
        match = DENIED_GLOSS_ANY_SENSE.search(sense.definition)
        if match:
            fail("denied-gloss", f"{sense.synset} definition mentions '{match.group(0)}'")

    if primary is not None and word not in overrides.allowed_adjectives:
        flagged_ancestors = primary.ancestors & DENIED_ANCESTORS_PRIMARY_SENSE
        if flagged_ancestors:
            fail(
                "denied-primary-hypernym",
                f"main sense {primary.synset} is a {', '.join(sorted(flagged_ancestors))}",
            )
        match = DENIED_GLOSS_PRIMARY_SENSE.search(primary.definition)
        if match:
            fail(
                "denied-primary-gloss",
                f"main sense {primary.synset} definition mentions '{match.group(0)}'",
            )

    return _dedupe(reasons)


_POS_NAMES = {"v": "a verb", "a": "an adjective", "r": "an adverb", "n": "a noun"}


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def close_spelling(a: str, b: str) -> bool:
    """One edit apart, or two when both words have 6+ letters.

    Short words two edits apart are usually different words ('pool'/'pond').
    """
    distance = edit_distance(a, b)
    return distance <= 1 or (distance == 2 and min(len(a), len(b)) >= 6)


def find_duplicates(
    words: Iterable[str],
    synsets_of: Mapping[str, frozenset],
    drop_priority: Callable[[str], tuple],
) -> dict[str, str]:
    """Find spelling variants and exact synonyms; return dropped -> kept.

    Two words are duplicates when they have identical WordNet senses
    ('cougar'/'puma'), or when one's senses are a subset of the other's and
    the spellings are close ('racoon'/'raccoon', 'sulphate'/'sulfate'; see
    ``close_spelling``). Merely sharing a sense is not enough: 'house' and
    'home' share one but mean different things. The word with the lower
    ``drop_priority`` is kept.
    """
    ordered = sorted(words, key=drop_priority)
    kept: list[str] = []
    dropped: dict[str, str] = {}
    for word in ordered:
        mine = synsets_of[word]
        twin = next(
            (
                other
                for other in kept
                if synsets_of[other] == mine
                or (
                    mine & synsets_of[other]
                    and (mine <= synsets_of[other] or synsets_of[other] <= mine)
                    and close_spelling(other, word)
                )
            ),
            None,
        )
        if twin is None:
            kept.append(word)
        else:
            dropped[word] = twin
    return dropped


def _dedupe(reasons: Iterable[Reason]) -> list[Reason]:
    seen: set[Reason] = set()
    unique: list[Reason] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            unique.append(reason)
    return unique


# --- Combination screening --------------------------------------------------


COMPOUND_DENIED_PRIMARY_ANCESTORS = frozenset(
    {"ammunition.n.01", "explosive.n.01", "explosive_device.n.01", "weapon.n.01"}
)


def unsafe_compound_reason(senses: Sequence[Sense]) -> Optional[Reason]:
    """Why a WordNet compound such as 'couch_potato' is unsafe, or None.

    Narrower than ``evaluate_word``: compound definitions are often technical
    ('bell toad' mentions a copulatory organ), so gloss keywords are not used.
    Any compound naming a kind of person is unsafe - that is exactly the
    'big' + 'sister' pattern. Body-part compounds only count when WordNet
    labels the usage (e.g. colloquial 'bay window' for a paunch).
    """
    common = common_senses(senses)
    for sense in common:
        if sense.pos != "n":
            continue
        if sense.lexname == "noun.person":
            return Reason("denied-category", f"{sense.synset} names a kind of person")
        if sense.lexname in DENIED_NOUN_CATEGORIES and sense.usage_domains:
            return Reason("denied-category", f"{sense.synset} is colloquial {sense.lexname}")
    for sense in common:
        flagged = sense.usage_domains & DENIED_USAGE_DOMAINS
        if flagged:
            return Reason("usage-label", f"{sense.synset} labelled {', '.join(sorted(flagged))}")
        flagged = sense.ancestors & DENIED_ANCESTORS_ANY_SENSE
        if flagged:
            return Reason("denied-hypernym", f"{sense.synset} is a {', '.join(sorted(flagged))}")
    primary = primary_noun_sense(common)
    if primary is not None:
        flagged = primary.ancestors & COMPOUND_DENIED_PRIMARY_ANCESTORS
        if flagged:
            return Reason("denied-primary-hypernym", f"main sense {primary.synset} is a {', '.join(sorted(flagged))}")
    return None


@dataclass(frozen=True)
class Conflict:
    words: tuple  # the accepted words that together form the problem
    kind: str  # "phrase", "compound" or "boundary"
    detail: str


def find_phrase_conflicts(
    accepted: Iterable[str],
    phrases: Iterable[tuple[tuple[str, ...], str]],
    normalize: Callable[[str], str],
) -> list[Conflict]:
    """Flag phrases (e.g. 'golden shower') whose every token is an accepted word.

    ``normalize`` maps a token to the key used to match accepted words (the
    stemmer), so plural phrase tokens still match singular list words.
    """
    by_key = {normalize(word): word for word in accepted}
    conflicts: list[Conflict] = []
    seen: set[tuple[str, ...]] = set()
    for tokens, source in phrases:
        if len(tokens) < 2:
            continue
        matched = [by_key.get(normalize(token)) for token in tokens]
        if any(word is None for word in matched):
            continue
        words = tuple(dict.fromkeys(matched))  # dedupe, keep order
        if words in seen:
            continue
        seen.add(words)
        conflicts.append(Conflict(words, "phrase", f"'{' '.join(tokens)}' ({source})"))
    return conflicts


def find_compound_conflicts(
    accepted: Iterable[str],
    compounds: Iterable[tuple[str, str]],
    normalize: Callable[[str], str],
) -> list[Conflict]:
    """Flag closed compounds (e.g. 'pothead') that split into two accepted words.

    ``compounds`` holds (compound, source) pairs. The second half is
    normalized so a plural compound ('potheads') still matches 'head'.
    """
    accepted_set = set(accepted)
    by_key = {normalize(word): word for word in accepted_set}
    conflicts: list[Conflict] = []
    seen: set[tuple[str, str]] = set()
    for compound, source in compounds:
        for split in range(MIN_WORD_LENGTH, len(compound) - MIN_WORD_LENGTH + 1):
            first = compound[:split]
            second = by_key.get(normalize(compound[split:]))
            if first not in accepted_set or second is None or (first, second) in seen:
                continue
            seen.add((first, second))
            conflicts.append(Conflict((first, second), "compound", f"'{compound}' ({source})"))
    return conflicts


def find_boundary_conflicts(accepted: Sequence[str], terms: Iterable[str]) -> list[Conflict]:
    """Flag ordered pairs where an offensive term spans the join of two words.

    Only the join matters (e.g. 'X' + 'Y' -> '...xy...'): a term fully inside
    one word was already handled by the single-word rules.
    """
    words = list(accepted)
    by_suffix: dict[str, list[str]] = {}
    by_prefix: dict[str, list[str]] = {}
    for word in words:
        for size in range(1, len(word) + 1):
            by_suffix.setdefault(word[-size:], []).append(word)
            by_prefix.setdefault(word[:size], []).append(word)

    conflicts: list[Conflict] = []
    seen: set[tuple[str, str]] = set()
    for term in sorted(set(terms)):
        for split in range(1, len(term)):
            head, tail = term[:split], term[split:]
            for first in by_suffix.get(head, ()):
                for second in by_prefix.get(tail, ()):
                    if first == second or (first, second) in seen:
                        continue
                    seen.add((first, second))
                    conflicts.append(
                        Conflict((first, second), "boundary", f"'{first}{second}' contains '{term}'")
                    )
    return conflicts


def resolve_conflicts(
    conflicts: Iterable[Conflict], drop_priority: Callable[[str], tuple]
) -> dict[str, list[Conflict]]:
    """Choose words to drop so that no conflict remains.

    Greedy: repeatedly drop the word involved in the most unresolved
    conflicts; ties drop the word with the highest ``drop_priority`` (the
    less common one). Returns dropped word -> conflicts that caused it.
    """
    remaining = list(conflicts)
    dropped: dict[str, list[Conflict]] = {}
    while remaining:
        degree: dict[str, int] = {}
        for conflict in remaining:
            for word in set(conflict.words):
                degree[word] = degree.get(word, 0) + 1
        victim = max(degree, key=lambda word: (degree[word], drop_priority(word)))
        dropped[victim] = [c for c in remaining if victim in c.words]
        remaining = [c for c in remaining if victim not in c.words]
    return dropped


# --- Dice formatting --------------------------------------------------------


def dice_codes(dice: int) -> list[str]:
    return ["".join(roll) for roll in itertools.product("123456", repeat=dice)]


def format_dice_list(words: Sequence[str], dice: int) -> list[str]:
    codes = dice_codes(dice)
    if len(words) != len(codes):
        raise ValueError(f"{dice} dice need exactly {len(codes)} words, got {len(words)}")
    return [f"{code}\t{word}" for code, word in zip(codes, sorted(words))]
