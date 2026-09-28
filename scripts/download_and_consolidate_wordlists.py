#!/usr/bin/env python3
"""Download selected English wordlists, consolidate them, and report stats."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


WORD_PATTERN = re.compile(r"^[a-z]+$")


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    parser: str
    local_filename: str


SOURCES: tuple[Source, ...] = (
    Source(
        name="asian_diceware_7776_en",
        url="https://raw.githubusercontent.com/anoni-net/asian-diceware/main/output/asian_diceware_7776.txt",
        parser="plain",
        local_filename="asian_diceware_7776.txt",
    ),
    Source(
        name="eff_large_en",
        url="https://raw.githubusercontent.com/ulif/diceware/master/diceware/wordlists/wordlist_en_eff.txt",
        parser="eff_tab",
        local_filename="eff_large_wordlist.txt",
    ),
    Source(
        name="bip39_english",
        url="https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt",
        parser="plain",
        local_filename="bip39_english.txt",
    ),
)


def parse_words(content: str, parser: str) -> list[str]:
    words: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if parser == "eff_tab":
            if "\t" in line:
                _, candidate = line.split("\t", maxsplit=1)
            else:
                parts = line.split()
                candidate = parts[-1]
        else:
            candidate = line

        word = candidate.strip().lower()
        if WORD_PATTERN.match(word):
            words.append(word)

    return words


def stem_word(word: str) -> str:
    """Return a conservative English stem for counting/aggregation use."""
    stem = word

    if len(stem) <= 3:
        return stem

    if stem.endswith("ies") and len(stem) > 4:
        candidate = stem[:-3] + "y"
        if WORD_PATTERN.match(candidate):
            return candidate

    if stem.endswith("s") and len(stem) > 3 and not stem.endswith(("ss", "us", "is")):
        candidate = stem[:-1]
        if WORD_PATTERN.match(candidate) and len(candidate) >= 3:
            return candidate

    return stem


def unique_after_stemming(words: list[str]) -> dict[str, str]:
    """Map stem -> representative word (alphabetically smallest variant)."""
    stem_to_word: dict[str, str] = {}

    for word in words:
        stem = stem_word(word)
        current = stem_to_word.get(stem)
        if current is None or word < current:
            stem_to_word[stem] = word

    return stem_to_word


def download_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "safe-words-for-diceware/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        match = re.search(r"charset=([^;\s]+)", content_type, re.IGNORECASE)
        charset = match.group(1).strip('"').strip("'") if match else "utf-8"
        return response.read().decode(charset, errors="replace")



def display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)

def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(f"{line}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download selected English wordlists, consolidate them, and emit stats."
        )
    )
    parser.add_argument(
        "--output-dir",
        default="wordlists/generated",
        help="Directory for generated outputs (default: wordlists/generated)",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    requested_output = Path(args.output_dir)
    if requested_output.is_absolute():
        output_dir = requested_output.resolve()
    else:
        output_dir = (repo_root / requested_output).resolve()
    downloads_dir = output_dir / "downloads"

    consolidated_stem_to_word: dict[str, str] = {}
    source_stats: list[dict[str, object]] = []

    for source in SOURCES:
        content = download_text(source.url)
        downloaded_path = downloads_dir / source.local_filename
        downloaded_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded_path.write_text(content, encoding="utf-8")

        words = parse_words(content, source.parser)
        stem_to_word = unique_after_stemming(words)

        unique_stems = sorted(stem_to_word.keys())
        unique_words_after_stemming = sorted(stem_to_word.values())

        for stem, word in stem_to_word.items():
            current = consolidated_stem_to_word.get(stem)
            if current is None or word < current:
                consolidated_stem_to_word[stem] = word

        per_source_unique_path = output_dir / "by-source" / f"{source.name}.txt"
        per_source_stem_path = output_dir / "by-source-stems" / f"{source.name}.txt"
        write_lines(per_source_unique_path, unique_words_after_stemming)
        write_lines(per_source_stem_path, unique_stems)

        source_stats.append(
            {
                "name": source.name,
                "url": source.url,
                "word_count": len(words),
                "unique_word_count": len(set(words)),
                "stemmed_word_count": len(words),
                "post_stem_unique_word_count": len(unique_words_after_stemming),
                "unique_stem_count": len(unique_stems),
                "uniqueness_rule": "lowercase -> stem -> unique",
                "output_file": display_path(per_source_unique_path, repo_root),
                "stems_output_file": display_path(per_source_stem_path, repo_root),
            }
        )

    consolidated_stems = sorted(consolidated_stem_to_word.keys())
    consolidated_words = sorted(consolidated_stem_to_word.values())

    consolidated_words_path = output_dir / "consolidated-english-words.txt"
    consolidated_stems_path = output_dir / "consolidated-english-stems.txt"
    write_lines(consolidated_words_path, consolidated_words)
    write_lines(consolidated_stems_path, consolidated_stems)

    stats = {
        "sources": source_stats,
        "total_sources": len(SOURCES),
        "uniqueness_rule": "lowercase -> stem -> unique",
        "consolidated_unique_word_count": len(consolidated_words),
        "consolidated_unique_stem_count": len(consolidated_stems),
        "consolidated_output_file": display_path(consolidated_words_path, repo_root),
        "consolidated_stems_output_file": display_path(consolidated_stems_path, repo_root),
    }

    stats_path = output_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote consolidated words to: {consolidated_words_path}")
    print(f"Wrote consolidated stems to: {consolidated_stems_path}")
    print(f"Wrote stats to: {stats_path}")


if __name__ == "__main__":
    main()
