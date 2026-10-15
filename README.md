# safe-words-for-diceware

An English wordlist for Diceware-style passphrases where every word is safe
in a workplace on its own **and** in random combination with the others.
"Safe" means non-offensive to any group, acceptable in a company setting,
and free of negative connotations. For example, `big` and `sister` are each
harmless but `big sister` is not, so this list contains neither.

> **Review status.** The rules, filters and category choices were proposed
> by AI and approved by the maintainer in October 2026. Later changes need
> the same human review (see the AI-use policy below).

## The lists

| File | Words | Bits/word | Use |
|---|---|---|---|
| [`wordlists/safe-words.txt`](wordlists/safe-words.txt) | 1,763 | 10.8 | Software generators (`secrets.choice`) |
| [`wordlists/safe-diceware-1296.txt`](wordlists/safe-diceware-1296.txt) | 1,296 | 10.3 | Physical dice: roll 4 dice per word |

The dice list holds the 1,296 most common words of the full list.

**How many words to use.** Safety-first lists are smaller than general ones,
so use more words:

| Passphrase | Strength |
|---|---|
| 8 words from the full list | ~86 bits |
| 8 words from the dice list | ~83 bits |
| 6 words from the EFF large list | ~78 bits (for comparison) |

**Always join words with a separator**, such as a space or `-`. Words run
together can form other words across the join; "therapist" reads as "the
rapist". The build drops the most severe of these joins, but a separator
avoids all of them.

Example: `canyon-tulip-lantern-glacier-otter-saucer-meadow-kettle`

## How words are chosen

Every word comes from **Open English WordNet** and must pass three layers.
Full details and measurements are in
[`docs/selection-model.md`](docs/selection-model.md).

1. **Positive model.** Only common nouns are eligible, and only from
   low-risk categories: plants, landforms, water, weather, materials,
   shapes, structures, devices, vehicles, and most animals and foods.
   Categories whose words often describe people or bodies are excluded:
   clothing, hoofed and farm animals, primates, tools, meat and baked goods.
   Verbs, adverbs and adjectives are excluded. "Common" means **SCOWL**
   lists the word at size 40 or below, or at size 50 with evidence that
   people know it: SCOWL's ESL-learner or UK-frequency sources, or WordNet's
   sense-tagged corpus. This keeps `lantern` and `parsnip` but drops
   dictionary-only words like `bast` and `percale`.
2. **Safety rules.** A word is rejected if any meaning can describe a person
   or body, is labelled obscene, slur or disparaging, or is about sex, drugs,
   alcohol, violence, death, religion, disease or a country. It is also
   rejected if it appears in the LDNOOBW or dsojevic profanity lists, or is
   gendered or a verb form. Duplicates are removed: spelling variants,
   exact synonyms, and words sharing a stem (lowercase → Snowball stem →
   unique, so `stair`/`stairs` and `house`/`housing` keep one word).
3. **Combination screening.** Pairs of words are checked against the
   multi-word entries of the profanity lists, unsafe WordNet compounds
   (`couch potato`, `night owl`, `fruitcake`) and `filters/phrase-denylist.txt`.
   Joins that spell a severe slur or obscenity are also checked. One word of
   every flagged pair is dropped.

Human-reviewable decisions live in `filters/`:

| File | Contents |
|---|---|
| `categories.txt` | Allowed and denied WordNet categories (the positive model) |
| `denylist.txt` | Words removed in review, each with a category and reason |
| `phrase-denylist.txt` | Known problem phrases that no tool flags |
| `rule-waivers.txt` | Words whose automated rejection was a false positive, with justification |

## Reviewing

Every candidate, accepted or not, is in `review/word-decisions.tsv` with its
category, main WordNet definition, and the rules it failed. Combination
drops are in `review/combination-conflicts.tsv`, and counts are in
`review/stats.json`.

To change the list, edit `filters/` and rebuild. The review step is plain
data, so a person or a low-cost classification model can propose denylist
entries from `word-decisions.tsv`, followed by human spot checks.

## Building

Requires Python 3.10+ and NLTK.

```bash
pip install -r requirements.txt
python scripts/build_safe_wordlist.py            # downloads pinned inputs to build/
python scripts/build_safe_wordlist.py --offline  # reuse the downloads
python -m unittest discover tests
```

All inputs are pinned to a commit and verified by SHA-256, so a rebuild
reproduces the committed lists exactly. The size/familiarity trade-off is
measured in [`docs/selection-model.md`](docs/selection-model.md#commonness-and-size).

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

Any generated list is treated as a draft until manually reviewed. The current
`filters/` entries and category choices were proposed by AI and approved by
the maintainer in October 2026.

## License

| Files | License |
|---|---|
| Code: `scripts/`, `tests/`, `.github/` | [MIT](LICENSE-MIT) |
| Everything else: `wordlists/`, `review/`, `filters/` and the documentation | [CC BY 4.0](LICENSE-CC-BY-4.0) |

The wordlists are derived from Open English WordNet and filtered with SCOWL,
so any copy must also carry the notices in [`ATTRIBUTION.md`](ATTRIBUTION.md).
A suitable credit line:

> Wordlist from [safe-words-for-diceware](https://github.com/cbyrd01/safe-words-for-diceware)
> by Christopher Byrd, CC BY 4.0. Derived from Open English WordNet
> (CC BY 4.0) and SCOWL; see ATTRIBUTION.md.

## Sources and attribution

See [`sources/sources-and-licenses.md`](sources/sources-and-licenses.md) for
every input, its license, and the sources evaluated and rejected. Required
notices are in [`ATTRIBUTION.md`](ATTRIBUTION.md).
