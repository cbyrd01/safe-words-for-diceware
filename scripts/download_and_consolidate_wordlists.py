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


WORD_PATTERN = re.compile(r"^[a-z][a-z'\-]*$")


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
            # EFF format: "12345<TAB>word"
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


def download_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "safe-words-for-diceware/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="strict")


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
    output_dir = (repo_root / args.output_dir).resolve()
    downloads_dir = output_dir / "downloads"

    consolidated: set[str] = set()
    source_stats: list[dict[str, object]] = []

    for source in SOURCES:
        content = download_text(source.url)
        downloaded_path = downloads_dir / source.local_filename
        downloaded_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded_path.write_text(content, encoding="utf-8")

        words = parse_words(content, source.parser)
        unique_words = sorted(set(words))
        consolidated.update(unique_words)

        per_source_unique_path = output_dir / "by-source" / f"{source.name}.txt"
        write_lines(per_source_unique_path, unique_words)

        source_stats.append(
            {
                "name": source.name,
                "url": source.url,
                "word_count": len(words),
                "unique_word_count": len(unique_words),
                "output_file": str(per_source_unique_path.relative_to(repo_root)),
            }
        )

    consolidated_words = sorted(consolidated)
    consolidated_path = output_dir / "consolidated-english-words.txt"
    write_lines(consolidated_path, consolidated_words)

    stats = {
        "sources": source_stats,
        "total_sources": len(SOURCES),
        "consolidated_unique_word_count": len(consolidated_words),
        "consolidated_output_file": str(consolidated_path.relative_to(repo_root)),
    }

    stats_path = output_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote consolidated words to: {consolidated_path}")
    print(f"Wrote stats to: {stats_path}")


if __name__ == "__main__":
    main()
