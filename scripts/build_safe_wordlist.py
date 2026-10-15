#!/usr/bin/env python3
"""Build the safe Diceware wordlists from Open English WordNet and SCOWL.

Candidates are WordNet nouns that SCOWL lists as common lowercase nouns.
Each candidate must pass the category gate and safety rules in
``safe_wordlist_rules.py`` plus the human-reviewed files in ``filters/``;
accepted words are then screened for unsafe two-word combinations.

All downloads are pinned to a commit and checked against a SHA-256, so a
rebuild sees exactly the reviewed inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import urllib.request
import warnings
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from scripts import safe_wordlist_rules as rules
except ImportError:  # executed as a file: python scripts/build_safe_wordlist.py
    import safe_wordlist_rules as rules


@dataclass(frozen=True)
class PinnedFile:
    name: str
    url: str
    sha256: str
    filename: str
    license: str


WORDNET = PinnedFile(
    name="Open English WordNet 2025+ (NLTK format)",
    url=(
        "https://raw.githubusercontent.com/nltk/nltk_data/"
        "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/corpora/english_wordnet.zip"
    ),
    sha256="d5441a8972de29d18559068eb2c1004af864b1921adb5cb0958f7b9e4dacc802",
    filename="english_wordnet.zip",
    license="CC BY 4.0 and the Princeton WordNet License",
)
SCOWL = PinnedFile(
    name="SCOWL / English Speller Database",
    url=(
        "https://raw.githubusercontent.com/en-wl/wordlist/"
        "1e5b7d3a72f47a71da5d28686c1dd4b397178485/data/scowl-pre.txt"
    ),
    sha256="a5fe3f11682a6ab9d31f2ea2a185833b1a01be7af83409c671bd0756a870f6c7",
    filename="scowl-pre.txt",
    license="SCOWL copyright notice (permissive)",
)
LDNOOBW = PinnedFile(
    name="List of Dirty, Naughty, Obscene, and Otherwise Bad Words (en)",
    url=(
        "https://raw.githubusercontent.com/LDNOOBW/"
        "List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/"
        "5faf2ba42d7b1c0977169ec3611df25a3c08eb13/en"
    ),
    sha256="af851ecef1d5f212caba17339b12ac39cc2fef7d78c74876f67237644fcee8bd",
    filename="ldnoobw_en.txt",
    license="CC BY 4.0",
)
DSOJEVIC = PinnedFile(
    name="dsojevic/profanity-list (en)",
    url=(
        "https://raw.githubusercontent.com/dsojevic/profanity-list/"
        "c27924319aa9bd6f917e3782b4f4b6604a50b652/en.json"
    ),
    sha256="bcf8bfc09dd3f7480972cb041a4cba291a6ff16a6fbf29022d5d679e3c39502c",
    filename="dsojevic_profanity_en.json",
    license="MIT",
)

# SCOWL sizes: 35 small, 40, 50 medium, 60 medium-large, 70 large.
DEFAULT_MAX_SCOWL_SIZE = 50
# Familiarity: words up to size 40 always count as familiar. Size-50 words
# need evidence: listed in SCOWL's ESL-learner or UK-frequency sources, or
# attested in WordNet's sense-tagged corpus. This drops dictionary-only words
# such as 'bast', 'percale' and 'aspic'.
FAMILIAR_SCOWL_SIZE = 40
FAMILIARITY_TAGS = frozenset({"3esl", "ukfreq"})

# Join screening ("zebra" + "pear" -> "zeb-rape-ar") only uses the most severe
# dsojevic terms of at least 4 letters. Milder or shorter terms ("spic" in
# "glass" + "picnic") occur across countless innocent joins; separators avoid
# them entirely.
BOUNDARY_TERM_MIN_SEVERITY = 4
BOUNDARY_TERM_MIN_LENGTH = 4

SCOWL_DENIED_USAGE = re.compile(r"^(offensive|vulgar)-")


# --- Inputs -----------------------------------------------------------------


def fetch(pinned: PinnedFile, cache_dir: Path, offline: bool) -> Path:
    """Return a verified local copy of ``pinned``, downloading if needed."""
    path = cache_dir / pinned.filename
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == pinned.sha256:
        return path
    if offline:
        sys.exit(f"--offline given but {path} is missing or stale; run once without --offline.")
    request = urllib.request.Request(pinned.url, headers={"User-Agent": "safe-words-for-diceware/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != pinned.sha256:
        sys.exit(f"{pinned.name}: checksum mismatch (got {digest}, expected {pinned.sha256})")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def load_wordnet(zip_path: Path):
    import nltk
    from nltk.corpus.reader.wordnet import WordNetCorpusReader

    class OewnReader(WordNetCorpusReader):
        def map_wn(self, version="wordnet"):
            # NLTK maps non-3.0 WordNets to Princeton WordNet 3.0 for
            # multilingual (OMW) lookups, which needs that corpus installed.
            # Nothing here uses OMW, so skip the mapping.
            return None

    root = zip_path.parent / "english_wordnet"
    marker = root / ".sha256"
    if not marker.exists() or marker.read_text().strip() != WORDNET.sha256:
        with zipfile.ZipFile(io.BytesIO(zip_path.read_bytes())) as archive:
            archive.extractall(zip_path.parent)
        marker.write_text(WORDNET.sha256 + "\n")
    # NLTK 3.10+ only opens corpora under nltk.data.path; register ours.
    if str(root.parent) not in nltk.data.path:
        nltk.data.path.insert(0, str(root.parent))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "multilingual functions are not available"
        return OewnReader(str(root), None)


@dataclass
class ScowlWord:
    size: int = 99  # smallest SCOWL size of a lowercase noun entry
    usage: set = field(default_factory=set)  # usage notes on any entry
    tags: set = field(default_factory=set)  # source tags on noun entries ('3esl', ...)


_SCOWL_VARIANT = re.compile(r"(?:[ABZCD_][.=?v~V@x-]?)(?: [ABZCD_][.=?v~V@x-]?)*(?: \{\d+\})?|\+")
_SCOWL_LEMMA = re.compile(
    r"^[-@!]?(?P<word>[^\s<{(]+?)[*@~!†-]?"
    r"(?: <(?P<pos>[^>/]*)(?:/[^>]*)?>)?(?: \{[^}]*\})?(?: \((?P<usage>[^)]*)\))?$"
)


def parse_scowl(text: str) -> dict[str, ScowlWord]:
    """Index SCOWL's scowl-pre.txt by lowercase lemma.

    Only US/unspecified-region entries in American (or universal) spelling
    count, so British variants such as 'colour' are not treated as common.
    See the format description in the SCOWL README.
    """
    words: dict[str, ScowlWord] = {}
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0]
        if not line or line.startswith("#") or ": " not in line:
            continue
        fields = line.split(": ")
        size = re.match(r"(\d+)\b", fields[0])
        if not size or re.search(r"\b(GB|CA|AU)\b", fields[0]):
            continue
        lemma_field = fields[1]
        if _SCOWL_VARIANT.fullmatch(lemma_field):
            if not re.search(r"[A_+]", lemma_field) or len(fields) < 3:
                continue
            lemma_field = fields[2]
        lemma = _SCOWL_LEMMA.match(lemma_field)
        if not lemma or not rules.WORD_PATTERN.match(lemma.group("word")):
            continue
        entry = words.setdefault(lemma.group("word"), ScowlWord())
        if lemma.group("usage"):
            entry.usage.add(lemma.group("usage"))
        if (lemma.group("pos") or "").startswith("n"):
            entry.size = min(entry.size, int(size.group(1)))
            entry.tags.update(re.findall(r"\[([^\]]*)\]", fields[0]))
    return words


def profanity_entries(pinned: PinnedFile, content: str) -> list[tuple[str, int]]:
    """Return (lowercase entry, severity 1-4) pairs.

    dsojevic entries carry a severity; '*' marks optional repeated letters
    and is dropped. LDNOOBW has no severities, so its entries count as 3.
    """
    if pinned is DSOJEVIC:
        return [
            (alternative.replace("*", "").strip().lower(), int(item["severity"]))
            for item in json.loads(content)
            for alternative in item["match"].split("|")
        ]
    return [(line.strip().lower(), 3) for line in content.splitlines() if line.strip()]


def tokens_of(entry: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[^a-z]+", entry.lower()) if t)


def read_entries(path: Path) -> list[tuple[str, str]]:
    """Parse a filters/*.txt file into (entry, comment) pairs."""
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        body, _, comment = raw.partition("#")
        body = " ".join(body.split()).lower()
        if body:
            entries.append((body, comment.strip()))
    return entries


def load_overrides(filters_dir: Path) -> rules.Overrides:
    denylist = {word: reason or "manual denylist" for word, reason in read_entries(filters_dir / "denylist.txt")}
    waivers = {}
    for body, _ in read_entries(filters_dir / "rule-waivers.txt"):
        word, _, rule_ids = body.partition(" ")
        waivers[word] = frozenset(r.strip() for r in rule_ids.split(",") if r.strip())
    return rules.Overrides(denylist=denylist, waivers=waivers)


def load_categories(path: Path, wn) -> dict[str, rules.CategoryRule]:
    categories = {}
    for body, comment in read_entries(path):
        action, synset_name = body.split()
        if action not in {"allow", "deny"}:
            sys.exit(f"{path}: unknown action '{action}'")
        synset = wn.synset(synset_name)  # raises if the id is wrong
        categories[synset_name] = rules.CategoryRule(
            synset=synset_name,
            allow=action == "allow",
            label=comment.split(":")[0].strip() or synset_name,
            depth=synset.min_depth(),
        )
    return categories


def senses_for(wn, lemma: str) -> list[rules.Sense]:
    """All WordNet senses whose lemma is exactly ``lemma`` (any case)."""
    senses = []
    for lemma_obj in wn.lemmas(lemma):
        if lemma_obj.name().lower() != lemma.lower():
            continue
        synset = lemma_obj.synset()
        ancestors = {synset.name()}
        ancestors.update(s.name() for s in synset.closure(lambda s: s.hypernyms() + s.instance_hypernyms()))
        usage = {d.name() for d in synset.usage_domains()}
        usage.update(d.name() for d in lemma_obj.usage_domains())
        senses.append(
            rules.Sense(
                synset=synset.name(),
                pos="a" if synset.pos() == "s" else synset.pos(),
                lexname=synset.lexname(),
                count=lemma_obj.count(),
                is_instance=bool(synset.instance_hypernyms()),
                is_proper=lemma_obj.name()[:1].isupper(),
                usage_domains=frozenset(usage),
                ancestors=frozenset(ancestors),
                definition=synset.definition(),
            )
        )
    return senses


def write_lines(path: Path, lines) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(f"{line}\n")


# --- Pipeline ---------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-scowl-size", type=int, default=DEFAULT_MAX_SCOWL_SIZE,
                        help=f"largest SCOWL size considered (default {DEFAULT_MAX_SCOWL_SIZE})")
    parser.add_argument("--dice", type=int, default=4, help="dice per word for the numbered list (default 4)")
    parser.add_argument("--offline", action="store_true", help="use cached downloads; never touch the network")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parent.parent
    cache = repo / "build" / "downloads"
    filters_dir = repo / "filters"

    from nltk.stem import SnowballStemmer

    # One normalisation everywhere: lowercase -> Snowball stem.
    stem = SnowballStemmer("english").stem
    wn = load_wordnet(fetch(WORDNET, cache, args.offline))
    scowl = parse_scowl(fetch(SCOWL, cache, args.offline).read_text(encoding="utf-8"))
    categories = load_categories(filters_dir / "categories.txt", wn)
    overrides = load_overrides(filters_dir)

    profanity: dict[str, tuple[int, str]] = {}  # entry -> (max severity, source)
    for pinned in (LDNOOBW, DSOJEVIC):
        content = fetch(pinned, cache, args.offline).read_text(encoding="utf-8")
        for entry, severity in profanity_entries(pinned, content):
            if entry and severity >= profanity.get(entry, (0, ""))[0]:
                profanity[entry] = (severity, pinned.name)
    # Single words match exactly or as a plural ('cunts' flags 'cunt'). Not by
    # stem: 'snowballing' is slang, 'snowball' is not.
    profane_words = {tokens_of(e)[0]: src for e, (_, src) in profanity.items() if len(tokens_of(e)) == 1}

    # Candidates: WordNet nouns that SCOWL lists as common lowercase nouns.
    candidates = sorted(
        word
        for word in {name.lower() for name in wn.all_lemma_names(pos="n")}
        if rules.WORD_PATTERN.match(word)
        and rules.MIN_WORD_LENGTH <= len(word) <= rules.MAX_WORD_LENGTH
        and word in scowl
        and scowl[word].size <= args.max_scowl_size
    )
    senses_by_word = {word: senses_for(wn, word) for word in candidates}

    def tagged_count(word: str) -> int:
        return sum(s.count for s in rules.common_senses(senses_by_word[word]))

    def familiar(word: str) -> bool:
        entry = scowl[word]
        return entry.size <= FAMILIAR_SCOWL_SIZE or bool(entry.tags & FAMILIARITY_TAGS) or tagged_count(word) > 0

    decisions: dict[str, list[rules.Reason]] = {}
    for word in candidates:
        reasons = rules.evaluate_word(word, senses_by_word[word], categories, overrides, wn.morphy(word, "v"))
        if not familiar(word) and "unfamiliar" not in overrides.waivers.get(word, frozenset()):
            reasons.append(rules.Reason(
                "unfamiliar",
                f"SCOWL size {scowl[word].size} with no learner-dictionary, frequency-list or WordNet-corpus evidence",
            ))
        flagged = sorted(note for note in scowl[word].usage if SCOWL_DENIED_USAGE.match(note))
        if flagged:
            reasons.insert(0, rules.Reason("scowl-usage", f"SCOWL marks it {', '.join(flagged)}"))
        hit = next((profane_words[form] for form in (word, word + "s", word + "es") if form in profane_words), None)
        if hit:
            reasons.insert(0, rules.Reason("profanity-list", f"listed in {hit}"))
        decisions[word] = reasons

    def drop_priority(word: str) -> tuple:
        """Larger = less desirable: rarer in SCOWL, rarer in WordNet's tagged
        corpus, longer. A hash breaks remaining ties without favouring letters."""
        return (scowl[word].size, -tagged_count(word), len(word), hashlib.sha256(word.encode()).hexdigest())

    def accepted() -> list[str]:
        return sorted(word for word, reasons in decisions.items() if not reasons)

    # Spelling variants and exact synonyms. Compare noun senses: a stray verb
    # sense ('crawfish' = retreat) should not hide a variant.
    synsets_of = {
        w: frozenset(s.synset for s in rules.common_senses(senses_by_word[w]) if s.pos == "n") for w in accepted()
    }

    def keep_priority(word: str, shared: frozenset) -> tuple:
        """Prefer the commoner word (SCOWL, then tagged corpus), then the one
        WordNet lists first in the shared senses ('raccoon' before 'racoon')."""
        headword_rank = min(
            (
                names.index(word)
                for names in ([n.lower() for n in wn.synset(s).lemma_names()] for s in shared)
                if word in names
            ),
            default=99,
        )
        return (scowl[word].size, -tagged_count(word), headword_rank) + drop_priority(word)[2:]

    for word, kept in rules.find_duplicates(list(synsets_of), synsets_of, keep_priority).items():
        decisions[word].append(rules.Reason("duplicate", f"variant or synonym of '{kept}'"))
    def stem_keep_priority(word: str) -> tuple:
        """Within a stem group prefer the commoner, then the shorter base word
        ('magnet' over 'magnetism')."""
        return (scowl[word].size, len(word), -tagged_count(word), drop_priority(word)[-1])

    for word, kept in rules.find_stem_duplicates(accepted(), stem, stem_keep_priority).items():
        decisions[word].append(rules.Reason("duplicate", f"same stem as '{kept}'"))

    # Combination screening
    safe = accepted()
    safe_set = set(safe)
    safe_stems = {stem(w) for w in safe}
    phrases = [(tokens_of(e), src) for e, (_, src) in profanity.items() if len(tokens_of(e)) > 1]
    phrases += [(tokens_of(e), f"filters/phrase-denylist.txt: {why}") for e, why in read_entries(filters_dir / "phrase-denylist.txt")]
    compounds = [(e, src) for e, (_, src) in profanity.items() if len(tokens_of(e)) == 1]

    def splits_into_safe_words(name: str) -> bool:
        return any(
            name[:i] in safe_set and stem(name[i:]) in safe_stems
            for i in range(rules.MIN_WORD_LENGTH, len(name) - rules.MIN_WORD_LENGTH + 1)
        )

    for lemma_name in wn.all_lemma_names():
        name = lemma_name.lower()
        parts = tokens_of(name)
        is_phrase = len(parts) == 2 and all(stem(p) in safe_stems for p in parts)
        is_compound = len(parts) == 1 and name.isalpha() and splits_into_safe_words(name)
        if not (is_phrase or is_compound):
            continue
        unsafe = rules.unsafe_compound_reason(senses_for(wn, lemma_name))
        if unsafe is None:
            continue
        source = f"WordNet '{lemma_name}': {unsafe.detail}"
        if is_phrase:
            phrases.append((parts, source))
        else:
            compounds.append((name, source))

    boundary_terms = [
        e for e, (severity, _) in profanity.items()
        if e.isalpha() and len(e) >= BOUNDARY_TERM_MIN_LENGTH and severity >= BOUNDARY_TERM_MIN_SEVERITY
    ]
    conflicts = (
        rules.find_phrase_conflicts(safe, phrases, stem)
        + rules.find_compound_conflicts(safe, compounds, stem)
        + rules.find_boundary_conflicts(safe, boundary_terms)
    )
    dropped = rules.resolve_conflicts(conflicts, drop_priority)
    for word, caused_by in dropped.items():
        decisions[word].append(rules.Reason("combination", "; ".join(f"{c.kind}: {c.detail}" for c in caused_by)))
    final = accepted()

    # Outputs
    dice_size = 6 ** args.dice
    if len(final) < dice_size:
        sys.exit(f"only {len(final)} safe words; {args.dice} dice need {dice_size}")
    dice_words = sorted(sorted(final, key=drop_priority)[:dice_size])
    write_lines(repo / "wordlists" / "safe-words.txt", final)
    write_lines(repo / "wordlists" / f"safe-diceware-{dice_size}.txt", rules.format_dice_list(dice_words, args.dice))

    def category_of(word: str) -> str:
        primary = rules.primary_noun_sense(rules.common_senses(senses_by_word[word]))
        if primary is None:
            return ""
        rule = rules.match_category(primary, categories)
        return rule.label if rule else primary.lexname

    def definition_of(word: str) -> str:
        primary = rules.primary_noun_sense(rules.common_senses(senses_by_word[word]))
        return primary.definition if primary else ""

    review = repo / "review"
    write_lines(
        review / "word-decisions.tsv",
        ["word\tdecision\tcategory\tscowl_size\trules\tdetails\tmain_definition"]
        + [
            "\t".join([
                word,
                "accepted" if not reasons else "excluded",
                category_of(word),
                str(scowl[word].size),
                ",".join(dict.fromkeys(r.rule for r in reasons)),
                " | ".join(r.detail for r in reasons),
                definition_of(word),
            ])
            for word, reasons in sorted(decisions.items())
        ],
    )
    write_lines(
        review / "combination-conflicts.tsv",
        ["words\tkind\tdetail\tdropped"]
        + [
            "\t".join([" + ".join(c.words), c.kind, c.detail, next(w for w in c.words if w in dropped)])
            for c in sorted(conflicts, key=lambda c: (c.kind, c.words))
        ],
    )

    first_rule = Counter(reasons[0].rule for reasons in decisions.values() if reasons)
    stats = {
        "candidates": len(candidates),
        "excluded_by_first_failing_rule": dict(first_rule.most_common()),
        "combination_conflicts": len(conflicts),
        "combination_drops": len(dropped),
        "safe_words": len(final),
        "safe_words_bits_per_word": round(math.log2(len(final)), 2),
        "dice_list_words": dice_size,
        "dice_list_bits_per_word": round(math.log2(dice_size), 2),
        "safe_words_by_category": dict(Counter(category_of(w) for w in final).most_common()),
        "max_scowl_size": args.max_scowl_size,
        "familiarity": {
            "always_familiar_up_to_scowl_size": FAMILIAR_SCOWL_SIZE,
            "evidence_tags": sorted(FAMILIARITY_TAGS),
            "or_wordnet_tagged_corpus": True,
        },
        "inputs": [
            {"name": p.name, "url": p.url, "sha256": p.sha256, "license": p.license}
            for p in (WORDNET, SCOWL, LDNOOBW, DSOJEVIC)
        ],
    }
    (review / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    print(f"{len(final)} safe words ({stats['safe_words_bits_per_word']} bits/word) -> wordlists/safe-words.txt")
    print(f"{dice_size}-word dice list -> wordlists/safe-diceware-{dice_size}.txt")
    print("Review reports -> review/")


if __name__ == "__main__":
    main()
