# safe-words-for-diceware

A curated wordlist project for combined Diceware-style passphrases, focused on words that are:
- non-offensive,
- acceptable in workplace/company settings,
- low risk for negative connotations both individually and when combined.

## AI use in this project (explicit policy)

AI is used as an **assistive tool** for:
- drafting candidate documentation,
- suggesting candidate words,
- proposing filtering rules.

AI output is **not accepted automatically**. Human review is required for:
- source/license decisions,
- inclusion/exclusion of words,
- combination-risk decisions,
- final publication.

Any generated list is treated as a draft until manually reviewed.

## Candidate sources and licensing

See `sources/sources-and-licenses.md` for the full source review (license, attribution needs, and curation/safety notes).

## Initial positive model

This project starts with a positive selection model:
- Prefer **nouns** (especially concrete objects, nature, animals) and a small set of neutral adjectives.
- Avoid **verbs** and **adverbs** (higher chance of problematic or suggestive combinations).
- Avoid relationship/power/political/medical/violent/drug/sexual terms.
- Exclude terms that are safe alone but often produce problematic compounds.

WordNet-style lexical categories are used as guidance for POS/type filtering (see source review document).

## Initial starter wordlist

A starter list is provided at:
- `wordlists/safe-words-v0.txt`

This is intentionally small and conservative to prioritize safety over size in the first revision.

## English source consolidation

Use `/home/runner/work/safe-words-for-diceware/safe-words-for-diceware/scripts/download_and_consolidate_wordlists.py` to:
- download selected English source lists,
- normalize and deduplicate per source,
- build a consolidated unique-word list,
- generate statistics output.

Generated outputs:
- `/home/runner/work/safe-words-for-diceware/safe-words-for-diceware/wordlists/generated/stats.json`
- `/home/runner/work/safe-words-for-diceware/safe-words-for-diceware/wordlists/generated/consolidated-english-words.txt`
- `/home/runner/work/safe-words-for-diceware/safe-words-for-diceware/wordlists/generated/by-source/*.txt`
