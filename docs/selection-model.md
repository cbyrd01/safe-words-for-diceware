# Selection model

How words are chosen, and the measurements behind each choice. All numbers
come from Open English WordNet 2025+ and the pinned inputs listed in
`sources/sources-and-licenses.md`. They were measured in October 2026.

## Why a positive model

Denylists alone fail in two ways. First, they never cover every slur, slang
term or innuendo: even a list curated for safety (Asian Diceware) shipped
`cunts` and `whores`. Second, they cannot judge pairs, because
`big` + `sister` contains no bad word.

A positive model instead admits only *types* of words that rarely go wrong,
alone or together, and uses denylists as a backstop.

## Which word types combine safely

WordNet records ~40,000 established two-word compounds (`couch potato`,
`night owl`). Restricting to compounds whose two words are each safe alone
shows how often pairing creates a problem:

| Pair | Compounds | Names a kind of person | Offensive / NSFW |
|---|---|---|---|
| noun + noun | 12,886 | 0.1% | 0.3% |
| adjective + noun | 5,206 | 0.4% | 1.0% |
| verb + noun | 793 | 0.4% | 0.9% |

Adjective + noun is about 3.5× as risky as noun + noun. Real incidents match:
- Docker's name generator removed adjectives about body size, mental health
  and intoxication.
- Ubuntu's petname removed `swine`, `donkey`, `man`, `cockatoo` and
  `peacock` "to avoid awkward professional combinations".

**So the list is nouns only.** Adjectives would add ~100 words, about
+0.04 bits/word, for that extra risk.

The single biggest risk is a word that can refer to a person: 37% of WordNet
compounds containing a person noun are unsafe. That is the `big sister`
mechanism, so any word with *any* person or body sense is rejected. Words
with many senses are riskier too: 11% of two-sense words carry a person,
body or offensive-usage sense, against 32% of words with ten or more senses.

## Category risk

For each category, the share of common words that carry a problematic second
meaning (a person, body, slur, sexual or drug sense), are part of an unsafe
WordNet compound, or appear in a profanity-list phrase:

| Category | Second meaning | Unsafe compound | Profanity phrase | Decision |
|---|---|---|---|---|
| minerals, gems | 6% | 0% | 0% | allow |
| decorations | 7% | 3% | 0% | allow |
| fabrics | 2% | 8% | 5% | allow |
| landforms | 4% | 15% | 2% | allow |
| bodies of water | 9% | 9% | 0% | allow |
| weather | 12% | 6% | 0% | allow |
| herbs, trees, flowers | 5–12% | 10–24% | 0–5% | allow |
| musical instruments | 5% | 29% | 5% | allow |
| vehicles | 6% | 17% | 8% | allow |
| insects | 17% | 9% | 4% | allow (review) |
| birds | 20% | 18% | 2% | allow (review) |
| containers | 19% | 19% | 9% | allow (review) |
| furniture | 31% | 41% | 0% | allow (review): `bed`, `chair`, `stool`, `throne` fail the person/body rules |
| buildings, rooms | 26–27% | 15–21% | 0% | allow (review) |
| clothing | 17% | 20% | 4% | **deny**: worn on the body |
| hoofed mammals | 19% | 30% | 16% | **deny**: `pig`, `cow`, `ass`, `goat`; gendered `mare` |
| meat | 19% | 25% | 12% | **deny** |
| tools and implements | 21% | 14% | 10% | **deny**: `knife`, `axe`; `rod`, `stick`, `pole` |
| liquids and drinks | 69% | 53% | 7% | allow; alcohol is rejected by rule |
| weapons; people, body, feelings | 100% | — | — | **deny** |

These rates are computed before any filtering, so they show how much
cleanup each category needs, not how risky the words that ship are.

Primates (`ape`, `monkey`), young animals (`kitten`, `filly`), pests,
parasites, footwear and hosiery, headwear and baked goods (`buns`,
`crumpet`) are also denied, because review found high residual risk after
the automated rules. The authoritative list is `filters/categories.txt`.

## Rules applied to every word

Rules marked † look only at the word's main (most frequent) sense.

| Rule | Rejects |
|---|---|
| category † | main sense outside an allowed category, or in a denied one |
| pos | words mostly used as verbs, adjectives or adverbs |
| denied-category | any sense in `noun.person`, `noun.body`, `noun.feeling` or `noun.motive` |
| usage-label | any sense labelled obscenity, ethnic slur, disparagement, drug street name or trademark |
| denied-hypernym | any sense under alcohol, drugs, tobacco, contraceptives, undergarments, sex toys, coffins, graves, execution or punishment |
| denied-gloss | any definition mentioning sex, genitals, excrement, slurs, murder, corpses, narcotics and similar |
| denied-primary-hypernym † | weapons, explosives, prisons, places of worship, holy days, toilets, poisons, military vehicles |
| denied-primary-gloss † | religion, weapons, killing, prison, disease, poison, alcohol, gambling, military |
| gendered † | definitions saying "male" or "female" (`rooster`, `lioness`) |
| proper-name | countries (`chile`, `panama`) and nationality adjectives |
| verb-form | verb forms with no attested noun use (`tore`, `seizing`) |
| profanity-list, scowl-usage | words on LDNOOBW or dsojevic (exact or plural match: `snowballing` is slang, `snowball` is not), or marked offensive or vulgar by SCOWL |
| duplicate | spelling variants (`racoon`), exact synonyms (`cougar`/`puma`), and words sharing a Snowball stem with a listed word (`stairs`, `housing`, `magnetism`); the commoner, then shorter, word is kept |
| unfamiliar | SCOWL size-50 words with no familiarity evidence (see below) |
| manual-denylist | review decisions in `filters/denylist.txt` |
| combination | one word of every flagged pair (see below) |

## Combination screening

Accepted words are checked as pairs, matching phrase words by Snowball stem
(so `brown showers` matches `brown` + `shower`):
- Every multi-word entry in the profanity lists and in
  `filters/phrase-denylist.txt`.
- Every WordNet compound, open (`couch potato`) or closed (`doormat`), that
  names a kind of person or falls in a denied topic.
- Every join of two words that spells a severity-4 dsojevic term, e.g.
  `zebra` + `pear` → "zeb**rape**ar".

Conflicts are resolved by dropping the word involved in the most of them;
ties drop the less common word.

## Commonness and size

WordNet is full of words few people know, so candidates must also be
familiar. Every safe word was scored against an independent proxy: whether
it occurs at all in a US TV and film frequency list (zxcvbn's, used only for
this evaluation). Options compared:

| Commonness filter | Words | Bits/word | Not in TV/film list |
|---|---|---|---|
| SCOWL size ≤ 35 | 1,455 | 10.5 | 15% |
| SCOWL size ≤ 40 | 1,591 | 10.6 | 17% |
| SCOWL size ≤ 50 | 2,634 | 11.4 | **40%** (`bast`, `percale`, `aspic`, `hominy`, `dacha`) |
| **≤ 40, or ≤ 50 with familiarity evidence (chosen)** | **1,763** | **10.8** | ~22% |
| SCOWL size ≤ 60 | ~3,400 | 11.7 | higher (`calcimine`, `reactance`, `refection`) |

"Familiarity evidence" means the word is in SCOWL's ESL-learner (`3esl`) or
UK-frequency (`ukfreq`) sources, or is attested in WordNet's sense-tagged
corpus. Words that fail get the `unfamiliar` rule. Other signals were tested
and rejected:
- Two or more WordNet senses adds 261 words, but they are mixed: `thyme`
  and `cumin`, but also `whelk`, `scrod` and `sump`.
- Short words add 178, mostly obscure (`bast`, `pipit`, `oakum`).

The proxy overstates obscurity: most chosen words missing from TV dialogue
are ordinary nouns (`birdbath`, `xylophone`, `ladybug`, `parasol`).

A familiar word that misses the signals (`thyme`, `hummus`) can be
restored with an `unfamiliar` waiver in `filters/rule-waivers.txt`. Allowing
10-letter words would add ~270 words (+0.1 bits/word); not worth the
length.

Passphrase strength comes from word count: each word adds 10.8 bits, so
8 words give ~86 bits.

## Review

The automated rules are a first pass; `filters/denylist.txt` holds review
decisions. Each review input row in `review/word-decisions.tsv` has the word,
its category, its main definition and its rule results. That is enough
context for a person, or a low-cost classification model, to propose
denylist entries with a category and reason. All entries need human sign-off
under the AI-use policy.
