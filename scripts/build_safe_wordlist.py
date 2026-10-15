#!/usr/bin/env python3
"""Filter the consolidated candidates into the safe Diceware wordlists.

Run ``download_and_consolidate_wordlists.py`` first. This script then:

1. loads Open English WordNet (via NLTK) and two profanity lists,
2. applies the rules in ``safe_wordlist_rules.py`` to every candidate,
3. screens accepted words for unsafe two-word combinations,
4. writes the full safe list, a numbered dice list, and review reports.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

try:
    from scripts import safe_wordlist_rules as rules
    from scripts.download_and_consolidate_wordlists import (
        SOURCES,
        display_path,
        download_text,
        stem_word,
        write_lines,
    )
except ImportError:  # executed as a file: python scripts/build_safe_wordlist.py
    import safe_wordlist_rules as rules
    from download_and_consolidate_wordlists import (
        SOURCES,
        display_path,
        download_text,
        stem_word,
        write_lines,
    )


# Open English WordNet 2025+ (CC BY 4.0) in NLTK's format, pinned to an
# nltk_data commit and checksum so every rebuild sees the same senses.
WORDNET_URL = (
    "https://raw.githubusercontent.com/nltk/nltk_data/"
    "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/corpora/english_wordnet.zip"
)
WORDNET_SHA256 = "d5441a8972de29d18559068eb2c1004af864b1921adb5cb0958f7b9e4dacc802"
WORDNET_DIRNAME = "english_wordnet"


@dataclass(frozen=True)
class Denylist:
    name: str
    url: str
    local_filename: str
    license: str


# Pinned to commits so a rebuild sees exactly the reviewed inputs.
DENYLISTS = (
    Denylist(
        name="ldnoobw_en",
        url=(
            "https://raw.githubusercontent.com/LDNOOBW/"
            "List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/"
            "5faf2ba42d7b1c0977169ec3611df25a3c08eb13/en"
        ),
        local_filename="ldnoobw_en.txt",
        license="CC BY 4.0",
    ),
    Denylist(
        name="dsojevic_profanity_en",
        url=(
            "https://raw.githubusercontent.com/dsojevic/profanity-list/"
            "c27924319aa9bd6f917e3782b4f4b6604a50b652/en.json"
        ),
        local_filename="dsojevic_profanity_en.json",
        license="MIT",
    ),
)

# Join screening ("zebra" + "pear" -> "zeb-rape-ar") only uses the most severe
# dsojevic terms of at least 4 letters. Milder or shorter terms ("spic" in
# "glass" + "picnic") occur across countless innocent joins; separators avoid
# them entirely.
BOUNDARY_TERM_MIN_SEVERITY = 4
BOUNDARY_TERM_MIN_LENGTH = 4


# --- Loading ----------------------------------------------------------------


def ensure_wordnet(downloads_dir: Path, offline: bool) -> Path:
    """Download and unpack the pinned WordNet once; return its directory."""
    root = downloads_dir / WORDNET_DIRNAME
    marker = root / ".sha256"
    if marker.exists() and marker.read_text().strip() == WORDNET_SHA256:
        return root
    if offline:
        sys.exit(f"--offline given but {root} is missing; run once without --offline.")
    request = urllib.request.Request(WORDNET_URL, headers={"User-Agent": "safe-words-for-diceware/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != WORDNET_SHA256:
        sys.exit(f"WordNet download checksum mismatch: got {digest}, expected {WORDNET_SHA256}")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(downloads_dir)
    marker.write_text(WORDNET_SHA256 + "\n")
    return root


def load_wordnet(root: Path):
    import nltk
    from nltk.corpus.reader.wordnet import WordNetCorpusReader

    # NLTK 3.10+ only opens corpora under nltk.data.path; register ours.
    if str(root.parent) not in nltk.data.path:
        nltk.data.path.insert(0, str(root.parent))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "multilingual functions are not available"
        return WordNetCorpusReader(str(root), None)


def senses_for(wn, lemma: str) -> list[rules.Sense]:
    """All WordNet senses whose lemma is exactly ``lemma`` (any case)."""
    senses = []
    for lemma_obj in wn.lemmas(lemma):
        if lemma_obj.name().lower() != lemma.lower():
            continue
        synset = lemma_obj.synset()
        ancestors = {synset.name()}
        ancestors.update(
            s.name() for s in synset.closure(lambda s: s.hypernyms() + s.instance_hypernyms())
        )
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


def read_entries(path: Path) -> list[tuple[str, str]]:
    """Parse a filters/*.txt file into (entry, comment) pairs."""
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        body, _, comment = raw.partition("#")
        body = body.strip().lower()
        if body:
            entries.append((body, comment.strip()))
    return entries


def load_overrides(filters_dir: Path) -> rules.Overrides:
    denylist = {word: reason or "manual denylist" for word, reason in read_entries(filters_dir / "denylist.txt")}
    adjectives = frozenset(word for word, _ in read_entries(filters_dir / "allowed-adjectives.txt"))
    waivers = {}
    for body, _ in read_entries(filters_dir / "rule-waivers.txt"):
        word, _, rule_ids = body.partition(" ")
        waivers[word] = frozenset(r.strip() for r in rule_ids.split(",") if r.strip())
    return rules.Overrides(denylist=denylist, allowed_adjectives=adjectives, waivers=waivers)


def fetch_denylist(denylist: Denylist, downloads_dir: Path, offline: bool) -> str:
    path = downloads_dir / denylist.local_filename
    if offline:
        if not path.exists():
            sys.exit(f"--offline given but {path} is missing; run once without --offline.")
        return path.read_text(encoding="utf-8")
    content = download_text(denylist.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return content


def profanity_entries(name: str, content: str) -> list[tuple[str, int]]:
    """Return (lowercase entry, severity 1-4) pairs.

    dsojevic entries carry a severity; '*' marks optional repeated letters
    and is dropped. LDNOOBW has no severities, so its entries count as 3.
    """
    if name.startswith("dsojevic"):
        entries = []
        for item in json.loads(content):
            for alternative in item["match"].split("|"):
                entries.append((alternative.replace("*", "").strip().lower(), int(item["severity"])))
        return entries
    return [(line.strip().lower(), 3) for line in content.splitlines() if line.strip()]


def tokens_of(entry: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[^a-z]+", entry) if t)


# --- Pipeline ---------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--generated-dir", default="wordlists/generated")
    parser.add_argument("--filters-dir", default="filters")
    parser.add_argument("--output-dir", default="wordlists")
    parser.add_argument("--review-dir", default="review")
    parser.add_argument("--dice", type=int, default=4, help="dice per word for the numbered list")
    parser.add_argument(
        "--wordnet-dir",
        help="use this unzipped english_wordnet corpus instead of the pinned download",
    )
    parser.add_argument(
        "--offline", action="store_true", help="use cached downloads; never touch the network"
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    def resolve(path: str) -> Path:
        candidate = Path(path)
        return candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()

    generated_dir = resolve(args.generated_dir)
    filters_dir = resolve(args.filters_dir)
    output_dir = resolve(args.output_dir)
    review_dir = resolve(args.review_dir)

    candidates_path = generated_dir / "consolidated-english-words.txt"
    if not candidates_path.exists():
        sys.exit(f"{candidates_path} not found; run download_and_consolidate_wordlists.py first.")
    candidates = candidates_path.read_text(encoding="utf-8").split()

    source_stems = {
        source.name: set((generated_dir / "by-source-stems" / f"{source.name}.txt").read_text(encoding="utf-8").split())
        for source in SOURCES
    }

    def sources_of(word: str) -> list[str]:
        return [name for name, stems in source_stems.items() if stem_word(word) in stems]

    downloads_dir = generated_dir / "downloads"
    wordnet_root = resolve(args.wordnet_dir) if args.wordnet_dir else ensure_wordnet(downloads_dir, args.offline)
    wn = load_wordnet(wordnet_root)
    overrides = load_overrides(filters_dir)

    profanity: dict[str, tuple[int, str]] = {}  # entry -> (max severity, source)
    for denylist in DENYLISTS:
        content = fetch_denylist(denylist, downloads_dir, args.offline)
        for entry, severity in profanity_entries(denylist.name, content):
            if entry and severity >= profanity.get(entry, (0, ""))[0]:
                profanity[entry] = (severity, denylist.name)
    profane_singles = {tokens_of(e)[0]: src for e, (_, src) in profanity.items() if len(tokens_of(e)) == 1}
    profane_stems = {stem_word(word): src for word, src in profane_singles.items()}

    # 1-2. Positive model and hard denials, per word
    senses_by_word = {word: senses_for(wn, word) for word in candidates}
    decisions: dict[str, list[rules.Reason]] = {}
    for word in candidates:
        reasons = rules.evaluate_word(word, senses_by_word[word], overrides, wn.morphy(word, "v"))
        hit = profane_singles.get(word) or profane_stems.get(stem_word(word))
        if hit:
            reasons.insert(0, rules.Reason("profanity-list", f"listed in {hit}"))
        decisions[word] = reasons

    def commonness(word: str) -> float:
        """Source agreement plus WordNet's tagged-corpus frequency."""
        tagged = sum(s.count for s in rules.common_senses(senses_by_word[word]))
        return 2 * len(sources_of(word)) + math.log2(1 + tagged)

    def drop_priority(word: str) -> tuple:
        """Larger = less desirable: less common, then longer. A hash breaks
        the remaining ties so selection does not favour early letters."""
        return (-commonness(word), len(word), hashlib.sha256(word.encode()).hexdigest())

    accepted = sorted(word for word, reasons in decisions.items() if not reasons)

    # Spelling variants and exact synonyms (armour/armor, racoon/raccoon).
    # Compare noun senses: a stray verb sense ('crawfish' = retreat) should
    # not hide a variant. Adjectives have none, so they use all senses.
    def comparable_synsets(word: str) -> frozenset:
        common = rules.common_senses(senses_by_word[word])
        nouns = frozenset(s.synset for s in common if s.pos == "n")
        return nouns or frozenset(s.synset for s in common)

    synsets_of = {w: comparable_synsets(w) for w in accepted}
    for word, kept in rules.find_duplicates(accepted, synsets_of, drop_priority).items():
        decisions[word].append(rules.Reason("duplicate", f"variant or synonym of '{kept}'"))
    accepted = sorted(word for word, reasons in decisions.items() if not reasons)

    # 3. Combination screening
    phrases = [(tokens_of(e), src) for e, (_, src) in profanity.items() if len(tokens_of(e)) > 1]
    phrases += [(tokens_of(e), f"filters/phrase-denylist.txt: {why}") for e, why in read_entries(filters_dir / "phrase-denylist.txt")]
    closed_compounds = [(e, src) for e, (_, src) in profanity.items() if len(tokens_of(e)) == 1]

    # WordNet compounds built from two accepted words, kept when unsafe.
    accepted_set = set(accepted)
    accepted_stems = {stem_word(w) for w in accepted}

    def splits_into_accepted(name: str) -> bool:
        return any(
            name[:i] in accepted_set and stem_word(name[i:]) in accepted_stems
            for i in range(rules.MIN_WORD_LENGTH, len(name) - rules.MIN_WORD_LENGTH + 1)
        )

    for lemma_name in wn.all_lemma_names():
        name = lemma_name.lower()
        parts = tokens_of(name)
        if len(parts) == 2 and all(stem_word(p) in accepted_stems for p in parts):
            target = "phrase"
        elif len(parts) == 1 and name.isalpha() and splits_into_accepted(name):
            target = "compound"
        else:
            continue
        unsafe = rules.unsafe_compound_reason(senses_for(wn, lemma_name))
        if unsafe is None:
            continue
        source = f"WordNet '{lemma_name}': {unsafe.detail}"
        if target == "phrase":
            phrases.append((parts, source))
        else:
            closed_compounds.append((name, source))

    boundary_terms = sorted(
        e for e, (severity, _) in profanity.items()
        if e.isalpha() and len(e) >= BOUNDARY_TERM_MIN_LENGTH and severity >= BOUNDARY_TERM_MIN_SEVERITY
    )
    conflicts = (
        rules.find_phrase_conflicts(accepted, phrases, stem_word)
        + rules.find_compound_conflicts(accepted, closed_compounds, stem_word)
        + rules.find_boundary_conflicts(accepted, boundary_terms)
    )
    dropped = rules.resolve_conflicts(conflicts, drop_priority)
    for word, caused_by in dropped.items():
        decisions[word].append(
            rules.Reason("combination", "; ".join(f"{c.kind}: {c.detail}" for c in caused_by))
        )
    final = sorted(word for word, reasons in decisions.items() if not reasons)

    # 4. Outputs
    dice_size = 6 ** args.dice
    if len(final) < dice_size:
        sys.exit(f"only {len(final)} safe words; {args.dice} dice need {dice_size}")
    dice_words = sorted(sorted(final, key=drop_priority)[:dice_size])

    safe_path = output_dir / "safe-words.txt"
    dice_path = output_dir / f"safe-diceware-{dice_size}.txt"
    write_lines(safe_path, final)
    write_lines(dice_path, rules.format_dice_list(dice_words, args.dice))

    decisions_path = review_dir / "word-decisions.tsv"
    write_lines(
        decisions_path,
        ["word\tdecision\tsources\trules\tdetails"]
        + [
            "\t".join(
                [
                    word,
                    "accepted" if not reasons else "excluded",
                    ",".join(sources_of(word)),
                    ",".join(dict.fromkeys(r.rule for r in reasons)),
                    " | ".join(r.detail for r in reasons),
                ]
            )
            for word, reasons in sorted(decisions.items())
        ],
    )
    combos_path = review_dir / "combination-conflicts.tsv"
    write_lines(
        combos_path,
        ["words\tkind\tdetail\tdropped"]
        + [
            "\t".join([" + ".join(c.words), c.kind, c.detail, next(w for w in c.words if w in dropped)])
            for c in sorted(conflicts, key=lambda c: (c.kind, c.words))
        ],
    )

    rule_counts: dict[str, int] = {}
    for reasons in decisions.values():
        for rule in dict.fromkeys(r.rule for r in reasons):
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
    stats = {
        "candidate_count": len(candidates),
        "excluded_by_rule": dict(sorted(rule_counts.items(), key=lambda kv: -kv[1])),
        "combination_conflicts": len(conflicts),
        "combination_drops": len(dropped),
        "safe_word_count": len(final),
        "safe_word_entropy_bits": round(math.log2(len(final)), 3),
        "dice_list_word_count": dice_size,
        "dice_list_entropy_bits": round(math.log2(dice_size), 3),
        "wordnet": {"version": f"Open English WordNet {wn.get_version()}", "url": WORDNET_URL, "sha256": WORDNET_SHA256},
        "denylists": [{"name": d.name, "url": d.url, "license": d.license} for d in DENYLISTS],
        "safe_words_file": display_path(safe_path, repo_root),
        "dice_list_file": display_path(dice_path, repo_root),
        "word_decisions_file": display_path(decisions_path, repo_root),
        "combination_conflicts_file": display_path(combos_path, repo_root),
    }
    stats_path = generated_dir / "safe-stats.json"
    stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    print(f"{len(final)} safe words ({stats['safe_word_entropy_bits']} bits/word) -> {safe_path}")
    print(f"{dice_size}-word dice list -> {dice_path}")
    print(f"Review reports -> {decisions_path}, {combos_path}")


if __name__ == "__main__":
    main()
