"""Selection rules for the safe Diceware wordlist.

Pure logic over plain records so it can be unit-tested without WordNet;
``build_safe_wordlist.py`` adapts WordNet and SCOWL into these records and
handles all I/O.

The model has three layers:

1. **Positive model (category gate)** - only nouns are eligible, and the
   word's main sense must fall under an *allowed* WordNet category such as
   animals, plants, landforms or furniture (``filters/categories.txt``).
   The most specific listed category decides, so "clothing" can be denied
   inside the allowed "covering" branch.
2. **Hard denials** - a word is rejected if *any* sense can describe a
   person or body, is labelled obscene / slur / disparaging, or belongs to a
   high-risk topic (sex, drugs, violence, ...). Lower-risk topics (weapons,
   religion, prisons) and gendered words are rejected when they are the
   word's *main* sense.
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

# A word with ANY common-noun sense in these lexicographer files is rejected:
# such words can describe a person or a body, which is where most
# "big" + "sister" style combinations get their meaning.
DENIED_NOUN_CATEGORIES = frozenset({"noun.body", "noun.feeling", "noun.motive", "noun.person"})

# WordNet usage labels that reject a word when found on any sense.
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

# Gendered words ('rooster', 'lioness', 'mare') invite gendered combinations.
GENDERED_GLOSS_PRIMARY_SENSE = re.compile(r"\b(female|male)\b", re.IGNORECASE)


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
class CategoryRule:
    """One line of filters/categories.txt."""

    synset: str
    allow: bool
    label: str
    depth: int  # WordNet depth; the deepest matching rule wins


@dataclass(frozen=True)
class Reason:
    rule: str
    detail: str


@dataclass(frozen=True)
class Overrides:
    """Human-reviewed exceptions loaded from the ``filters/`` directory."""

    denylist: Mapping[str, str] = field(default_factory=dict)
    # word -> rule ids that are waived for that word
    waivers: Mapping[str, frozenset] = field(default_factory=dict)


Stemmer = Callable[[str], str]  # the build uses NLTK's Snowball English stemmer


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


def match_category(sense: Sense, categories: Mapping[str, CategoryRule]) -> Optional[CategoryRule]:
    """The most specific category rule covering ``sense``. Deny wins ties;
    the synset name breaks any remaining tie so labels are deterministic."""
    matches = [categories[name] for name in sense.ancestors if name in categories]
    if not matches:
        return None
    return max(matches, key=lambda rule: (rule.depth, not rule.allow, rule.synset))


def evaluate_word(
    word: str,
    senses: Sequence[Sense],
    categories: Mapping[str, CategoryRule],
    overrides: Overrides,
    verb_base: Optional[str] = None,
) -> list[Reason]:
    """Return every rule the word fails. An empty list means accepted.

    ``verb_base`` is the verb the word inflects, if any ('shook' -> 'shake').
    """
    reasons: list[Reason] = []

    def fail(rule: str, detail: str) -> None:
        if rule not in overrides.waivers.get(word, frozenset()):
            reasons.append(Reason(rule, detail))

    if not WORD_PATTERN.match(word) or not MIN_WORD_LENGTH <= len(word) <= MAX_WORD_LENGTH:
        reasons.append(Reason("form", f"must be {MIN_WORD_LENGTH}-{MAX_WORD_LENGTH} letters a-z"))

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
    if not common or all(sense.is_proper for sense in common):
        reasons.append(Reason("not-in-wordnet", "no lowercase common-noun entry in WordNet"))
        return reasons

    # 1. Positive model: nouns only, main sense in an allowed category
    pos = dominant_pos(common)
    primary = primary_noun_sense(common)
    if pos != "n" or primary is None:
        fail("pos", f"mostly used as {_POS_NAMES.get(pos, pos)}, not a noun")
    else:
        rule = match_category(primary, categories)
        if rule is None:
            fail("category", f"main sense {primary.synset} ({primary.lexname}) is outside the allowed categories")
        elif not rule.allow:
            fail("category", f"main sense {primary.synset} is in denied category '{rule.label}'")

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

    if primary is not None:
        flagged_ancestors = primary.ancestors & DENIED_ANCESTORS_PRIMARY_SENSE
        if flagged_ancestors:
            fail("denied-primary-hypernym", f"main sense {primary.synset} is a {', '.join(sorted(flagged_ancestors))}")
        match = DENIED_GLOSS_PRIMARY_SENSE.search(primary.definition)
        if match:
            fail("denied-primary-gloss", f"main sense {primary.synset} definition mentions '{match.group(0)}'")
        match = GENDERED_GLOSS_PRIMARY_SENSE.search(primary.definition)
        if match:
            fail("gendered", f"main sense {primary.synset} definition mentions '{match.group(0)}'")

    return _dedupe(reasons)


_POS_NAMES = {"v": "a verb", "a": "an adjective", "r": "an adverb", "n": "a noun"}


def _dedupe(reasons: Iterable[Reason]) -> list[Reason]:
    return list(dict.fromkeys(reasons))


# --- Duplicates -------------------------------------------------------------


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


def is_duplicate_pair(a: str, b: str, synsets_of: Mapping[str, frozenset]) -> bool:
    """Identical WordNet senses ('cougar'/'puma'), or one word's senses are a
    subset of the other's and the spellings are close ('racoon'/'raccoon').
    Merely sharing a sense is not enough: 'house' and 'home' share one but
    mean different things."""
    mine, theirs = synsets_of[a], synsets_of[b]
    if not mine or not theirs:
        return False
    if mine == theirs:
        return True
    return bool(mine & theirs) and (mine <= theirs or theirs <= mine) and close_spelling(a, b)


def find_stem_duplicates(
    words: Iterable[str], stem: Stemmer, keep_priority: Callable[[str], tuple]
) -> dict[str, str]:
    """Words sharing a stem ('stair'/'stairs', 'house'/'housing'); keeping
    both invites recall mistakes. Each group keeps the word with the
    smallest ``keep_priority``. Returns dropped -> kept."""
    groups: dict[str, list[str]] = {}
    for word in sorted(words):
        groups.setdefault(stem(word.lower()), []).append(word)
    dropped: dict[str, str] = {}
    for group in groups.values():
        keeper = min(group, key=keep_priority)
        for word in group:
            if word != keeper:
                dropped[word] = keeper
    return dropped


def find_duplicates(
    words: Iterable[str],
    synsets_of: Mapping[str, frozenset],
    keep_priority: Callable[[str, frozenset], tuple],
) -> dict[str, str]:
    """Resolve spelling variants and exact synonyms; return dropped -> kept.

    Each duplicate pair keeps the word with the smaller
    ``keep_priority(word, shared_synsets)``, judged on the senses the pair
    shares (so 'hummus' beats 'humus' on the chickpea-dip sense even though
    'humus' heads its own soil sense). Pairs are resolved one at a time,
    strongest keeper first, and a word that already lost is not used again,
    so variant chains cannot spread: 'hammock' (bed) loses nothing because
    its variant 'hummock' is also a synonym of 'knoll'.
    """
    by_synset: dict[str, list[str]] = {}
    for word in sorted(words):
        for synset in synsets_of[word]:
            by_synset.setdefault(synset, []).append(word)
    pairs = {
        (a, b)
        for group in by_synset.values()
        for a, b in itertools.combinations(group, 2)
        if is_duplicate_pair(a, b, synsets_of)
    }

    def ranked(pair: tuple[str, str]) -> list[tuple[tuple, str]]:
        shared = synsets_of[pair[0]] & synsets_of[pair[1]]
        return sorted((keep_priority(word, shared), word) for word in pair)

    dropped: dict[str, str] = {}
    for pair in sorted(pairs, key=ranked):
        if pair[0] in dropped or pair[1] in dropped:
            continue
        (_, keeper), (_, loser) = ranked(pair)
        dropped[loser] = keeper
    return dropped


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
    stem: Stemmer,
) -> list[Conflict]:
    """Flag phrases (e.g. 'golden shower') whose every token is an accepted word.

    Tokens are matched by stem, so 'brown showers' still matches the words
    'brown' and 'shower'.
    """
    by_key = {stem(word): word for word in accepted}
    conflicts: list[Conflict] = []
    seen: set[tuple[str, ...]] = set()
    for tokens, source in phrases:
        if len(tokens) < 2:
            continue
        matched = [by_key.get(stem(token)) for token in tokens]
        if any(word is None for word in matched):
            continue
        words = tuple(dict.fromkeys(matched))
        if words in seen:
            continue
        seen.add(words)
        conflicts.append(Conflict(words, "phrase", f"'{' '.join(tokens)}' ({source})"))
    return conflicts


def find_compound_conflicts(
    accepted: Iterable[str],
    compounds: Iterable[tuple[str, str]],
    stem: Stemmer,
) -> list[Conflict]:
    """Flag closed compounds (e.g. 'pothead') that split into two accepted words.

    ``compounds`` holds (compound, source) pairs. The second half is matched
    by stem, so 'potheads' still matches 'head'.
    """
    accepted_set = set(accepted)
    by_key = {stem(word): word for word in accepted_set}
    conflicts: list[Conflict] = []
    seen: set[tuple[str, str]] = set()
    for compound, source in compounds:
        for split in range(MIN_WORD_LENGTH, len(compound) - MIN_WORD_LENGTH + 1):
            first = compound[:split]
            second = by_key.get(stem(compound[split:]))
            if first not in accepted_set or second is None or (first, second) in seen:
                continue
            seen.add((first, second))
            conflicts.append(Conflict((first, second), "compound", f"'{compound}' ({source})"))
    return conflicts


def find_boundary_conflicts(accepted: Sequence[str], terms: Iterable[str]) -> list[Conflict]:
    """Flag ordered pairs where an offensive term spans the join of two words.

    Only the join matters ('zebra' + 'pear' -> 'zeb-rape-ar'): a term fully
    inside one word was already handled by the single-word rules.
    """
    by_suffix: dict[str, list[str]] = {}
    by_prefix: dict[str, list[str]] = {}
    for word in accepted:
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
                    conflicts.append(Conflict((first, second), "boundary", f"'{first}{second}' contains '{term}'"))
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
