# Sources, licenses, and curation notes (English-only)

## Scope for this effort
This effort is restricted to **English** word lists only.

## Evaluation criteria
A source is considered "best" for this project when it has:
1. a permissive/reusable license,
2. clear attribution requirements,
3. explicit safety-aware curation (or clear evidence of offensive-term filtering),
4. enough vocabulary quality for Diceware-style passphrase generation.

## English candidate sources reviewed

### 1) Asian Diceware (English output)
- Source: https://github.com/anoni-net/asian-diceware
- English list used: `output/asian_diceware_7776.txt`
- License: data/wordlists are CC BY 4.0 (`LICENSE-DATA`); code is MIT.
- Attribution needed: yes (CC BY attribution + indicate changes).
- Safety curation: explicit "No offensive" acceptance criterion and profanity/slur-sensitive filtering in project spec/process.
- Verdict: **Best source** for this project's safety objective.

### 2) EFF large wordlist (English)
- Source (canonical): https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt
- Source used for automation reliability: https://raw.githubusercontent.com/ulif/diceware/master/diceware/wordlists/wordlist_en_eff.txt
- License: CC BY 3.0 (as documented in `ulif/diceware` COPYRIGHT for the EFF file).
- Attribution needed: yes (EFF + CC BY 3.0).
- Safety curation: curated for passphrase usability and includes avoidance rationale for problematic/confusable words, but not a full modern safety policy.
- Verdict: **Strong source** with attribution requirements.

### 3) BIP-39 English wordlist
- Source: `bitcoin/bips` (`bip-0039/english.txt`)
- License: MIT (BIP-39 spec license).
- Attribution needed: retain MIT notice in redistribution contexts.
- Safety curation: mnemonic quality and usability curation; not primarily social-safety curation.
- Verdict: **Good permissive baseline source**.

## English sources not selected as primary inputs

### Orchard Street "clean" Diceware list
- Source: https://github.com/sts10/orchard-street-wordlists
- Safety signal: explicit profanity exclusion.
- License: CC BY-SA 4.0.
- Why not primary: strong safety curation, but ShareAlike is less permissive than preferred for this repository's base source set.

## Selected source set for automation
The consolidation script uses these English sources:
1. Asian Diceware 7776 (CC BY 4.0)
2. EFF large wordlist (CC BY 3.0; fetched via GitHub mirror)
3. BIP-39 English (MIT)

## Notes
- Inclusion in the consolidated candidate list does **not** mean final acceptance.
- Additional manual safety review and combination-level screening are still required.
- Pre-filter consolidation can still include unsafe terms and must not be treated as a final safe list.

## Current consolidation results

Use `wordlists/generated/stats.json` for the current generated counts.

Reporting conventions in `stats.json`:
- `word_count`: total parsed words from the source list
- `stemmed_word_count`: number of words passed through stemming (pre-unique)
- `unique_word_count`: unique representative words after applying lowercase -> stem -> unique
- `unique_stem_count`: unique stems after applying lowercase -> stem -> unique
- `consolidated_unique_word_count`: unique representative words across all selected sources
- `consolidated_unique_stem_count`: unique stems across all selected sources

Result files (generated at runtime by the script):
- `wordlists/generated/consolidated-english-words.txt`
- `wordlists/generated/consolidated-english-stems.txt`
- `wordlists/generated/by-source/asian_diceware_7776_en.txt`
- `wordlists/generated/by-source/eff_large_en.txt`
- `wordlists/generated/by-source/bip39_english.txt`
- `wordlists/generated/by-source-stems/asian_diceware_7776_en.txt`
- `wordlists/generated/by-source-stems/eff_large_en.txt`
- `wordlists/generated/by-source-stems/bip39_english.txt`
