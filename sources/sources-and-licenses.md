# Sources, licenses, and curation notes

## Evaluation criteria
A source is considered "good" if it has:
1. a permissive or reusable license,
2. clear attribution requirements,
3. enough quality/curation to support safe-word filtering.

## Candidate sources

### 1) EFF large wordlist
- Source: https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt
- License (as redistributed in `ulif/diceware` COPYRIGHT): CC-BY-3.0
- Attribution needed: yes (Electronic Frontier Foundation and CC-BY notice)
- Safety curation: designed for memorable passphrases, **not specifically safety/non-offense curation**
- Verdict: **Good candidate source** with attribution obligations; requires additional safety filtering.

### 2) BIP-39 English wordlist
- Source: `bitcoin/bips` (`bip-0039/english.txt`), with BIP-39 spec listing `License: MIT`
- License: MIT (per BIP-39 document)
- Attribution needed: retain MIT license notice in redistribution contexts
- Safety curation: created for wallet mnemonic quality (distinctness/usability), **not social-safety curation**
- Verdict: **Good candidate source**; permissive and straightforward for reuse.

### 3) Open English WordNet (for lexical filtering/modeling)
- Source: https://github.com/globalwordnet/english-wordnet
- License: CC-BY-4.0, derived from Princeton WordNet with attribution requirements
- Attribution needed: yes (Open English WordNet + Princeton WordNet attribution)
- Safety curation: lexical graph resource; useful for POS/type categorization, not a safe-word list by itself
- Verdict: **Good supporting source** for modeling/filtering, not a standalone final list.

## Source choice for v0 list
For the initial `safe-words-v0.txt`, this repo uses a conservative subset based on BIP-39-style vocabulary and additional manual safety filtering.

## Positive model applied (v0)
- Include mostly concrete nouns and neutral adjectives.
- Exclude verbs and adverbs.
- Exclude terms related to violence, slurs, hate, exploitation, anatomy/sexual content, substances, coercion, and charged ideology.
- Exclude words likely to create problematic compounds when paired (for example role/kinship/power pairings).
