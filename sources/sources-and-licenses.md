# Sources, licenses and curation notes

The wordlists are built from a single word source, Open English WordNet.
Every other input is used only as a filter and contributes no words. All
inputs are pinned by commit and SHA-256 in `scripts/build_safe_wordlist.py`.

## Inputs used

| Input | Role | License | Attribution needed |
|---|---|---|---|
| [Open English WordNet](https://en-word.net/) 2025+ (NLTK format, [pinned](https://github.com/nltk/nltk_data/blob/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/corpora/english_wordnet.zip)) | **Word source.** Part of speech, categories (lexicographer files and hypernyms), usage labels, definitions | CC BY 4.0, plus the Princeton WordNet License for the underlying data | Yes: the OEWN team and Princeton University. See `ATTRIBUTION.md` |
| [SCOWL / English Speller Database](https://github.com/en-wl/wordlist) (`data/scowl-pre.txt`, pinned) | **Commonness filter.** Keeps nouns listed at size ≤ 40, or at size 50 when its ESL-learner (`3esl`) or UK-frequency (`ukfreq`) sources list them or WordNet's tagged corpus attests them; rejects words marked `offensive-*` or `vulgar-*` | Permissive: "Permission to use, copy, modify, distribute, and sell any part … or word lists created from it, is hereby granted without fee, provided that the above copyright notice appears in all copies" | Yes: keep the notice. See `ATTRIBUTION.md` |
| [LDNOOBW](https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words) `en` (pinned) | **Denylist.** Single words and multi-word phrases | CC BY 4.0 | Not redistributed. Credited in `ATTRIBUTION.md` |
| [dsojevic/profanity-list](https://github.com/dsojevic/profanity-list) `en.json` (pinned) | **Denylist** with severities; severity-4 terms are also checked across word joins | MIT | Not redistributed. Credited in `ATTRIBUTION.md` |

Curation notes:
- **WordNet** has no safety curation; its `noun.animal` file includes slurs
  such as `bitch`. It is used for its structure. The positive model and the
  safety rules do the filtering.
- **SCOWL** marks only "the worst offenders" as offensive or vulgar, so it
  cannot be the only safety net.
- **The profanity lists** catch modern slang that WordNet lacks. Neither is
  complete.

## Sources evaluated and rejected

These were considered as word sources. The checks behind the numbers below
were run in October 2026: each list was run through the profanity lists, and
the share of its words passing the positive model was measured.

| Source | License | Safety curation (as stated) | Finding | Verdict |
|---|---|---|---|---|
| Asian Diceware 7776 | CC BY 4.0 (data), MIT (code) | Spec lists a "No offensive" acceptance test | Contains `cunts`, `fucks`, `fucker`, `assholes`, `whores`, `rapists`, `retarded`, `dyke`. Only 14% pass the positive model | Rejected: its safety claim does not hold |
| EFF large wordlist | CC BY 3.0 US | "We manually checked and attempted to remove as many profane, insulting, sensitive, or emotionally-charged words as possible" | Contains `grope`, `hardcore`, `swinger`. 17% pass the positive model; 15% are person nouns | Rejected: general vocabulary |
| EFF short lists 1 and 2 | Same as above | Not confirmed for the short lists | List 1 contains `grope`, `panty`. 22% pass | Rejected |
| BIP-39 English | MIT | None stated for English | No profanity, but 26% verbs and 9% person nouns. 20% pass | Rejected |
| Glitch friendly-words | MIT | "All of the words and their generated pairings should be safe for children of all cultures" | Best curated list found (no profanity; 42% pass), but still includes `knife`, `sword`, `skull`, `church`, `eggplant`, and many dinosaur names | Rejected as a source |
| mnemonicode (Oren Tirosh) | MIT-style | Avoids offensive words *and* words "too likely to create combinations", religion, and negative meanings | Same goal as this project, but still contains `vodka`, `bikini`, `cartel` and proper names | Rejected; its method informed this model |
| Quick, Draw! categories; Ogden's 200 picturable nouns; picture-naming norms | CC BY 4.0 | Picturable by design | Small (200–1,300), and include weapons, toilets and skulls | Not needed: WordNet categories cover the same idea |
| Orchard Street, sts10 generated lists | CC BY-SA 4.0 | Profanity removed | ShareAlike is less permissive than wanted | Rejected on license |
| google-10000-english "no swears" | None | Swears removed | No license; still has `naked`, `kill`, `bomb` | Rejected |
| niceware, Pokerware, RFC 1751, PGP word list, Monero/Electrum lists | Various | None, or explicitly unchecked | Contain slurs or violence (`rape`, `coon`, `bomb`) | Rejected |

Psycholinguistic norms (concreteness, valence, age of acquisition) would make
good positive signals. They were not used because no clear permissive data
license could be confirmed for them; some (NRC VAD, the MRC database) appear
to be non-commercial.

## Output license

The generated lists are derived from Open English WordNet (CC BY 4.0) and
filtered with SCOWL. Anyone redistributing them must carry the notices in
`ATTRIBUTION.md`. This repository does not yet declare its own license.
