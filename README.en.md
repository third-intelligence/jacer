# jacer

[日本語](README.md) | English

A character error rate (CER) library for Japanese speech recognition that accounts for spelling and notation variants.

## Background

Speech recognition accuracy is usually measured as an error rate between a reference transcript and the recognizer's output (the hypothesis). Japanese has no spaces between words, so the error rate is counted in characters: the character error rate (CER). CER is the number of substitutions (S), deletions (D) and insertions (I) needed to turn the hypothesis into the reference, divided by the number of characters in the reference (N).

$$
\mathrm{CER} = \frac{S + D + I}{N}
$$

Japanese can write the same words in many ways. A number can be written in kanji or in Arabic digits, units and times have several notations, okurigana (the kana endings after a kanji) vary, and the same word can be written in kanji or in kana. Comparing the raw strings counts every one of these differences as an error, which makes it hard to measure how well a model actually recognizes speech.

For example, both of these are correct transcripts of the same utterance:

- Reference: `明日の三時半に二十キロの荷物が届くので、受け取ってください。`
- Hypothesis: `明日の3:30に20kgの荷物が届くので受取ってください`

Compared as raw strings, the time (`三時半` vs `3:30`) costs 4 characters, the number and unit (`二十キロ` vs `20kg`) another 4, the okurigana (`受け取って` vs `受取って`) 1, and the punctuation 2: 11 errors in 30 characters, a CER of about 37%.

jacer normalizes the two texts before comparing them, so differences in how numbers, units and times are written, in okurigana, in character width and in punctuation are not counted as errors. In the example above, `3:30`, `20kg` and `受取って` take the reference's notation, the punctuation is removed, and the CER is 0%.

## Normalization

The full rules are in [docs/metrics.en.md](docs/metrics.en.md). These are the main variants jacer resolves:

| | reference / hypothesis |
|---|---|
| width, punctuation, spaces | `ＡＢＣ` / `ABC`, `こんにちは。` / `こんにちは` |
| numbers | `三人` / `3人`, `二〇二六年` / `2026年`, `3万5000円` / `35,000円` |
| units | `5キロ` / `5km`, `50パーセント` / `50%` |
| times and money | `12時半` / `12:30`, `100ドル` / `$100` |
| Latin case | `iPhone` / `iphone` |
| okurigana | `申し込む` / `申込む` |
| small notation conventions | `3ヶ月` / `3か月`, `コンピューター` / `コンピュータ` |
| annotations in brackets | `そうですね(笑)` / `そうですね` |

## The three metrics

On top of this normalization, jacer provides three CER metrics that differ in what they accept as correct:

- **CER strict** (`cer_strict`, the primary metric) checks that the text matches the reference down to the choice of kanji or kana. `きょうはきれいなてんきです` for `今日は綺麗な天気です` is an error.
- **CER flex** (`cer_flex`) checks that the right words were transcribed, whatever mix of kanji and kana they are written in. The all-hiragana example above is correct, but writing `機会学習` for `機械学習`, a different word with the same sound, is an error.
- **CER kana** (`cer_kana`) converts both texts to katakana readings and compares those, checking that the right sounds were heard. `機会学習` and `機械学習` read the same, so they match. The readings come from OpenJTalk, so its reading mistakes carry into this metric.

Read together, the three metrics show where a model's errors come from: hearing the sounds (kana), choosing the words (flex), or choosing between kanji and kana (strict).

### Where the metrics differ

Edits for each pair (strict / flex / kana):

| reference / hypothesis | strict | flex | kana | why |
|---|---|---|---|---|
| `よろしくお願いします` / `よろしくおねがいします` | 2 | 0 | 0 | kanji vs kana, same word |
| `会議に参加します` / `かいぎにさんかします` | 6 | 0 | 0 | kanji vs kana, same words |
| `今日は暑いですね` / `きょうは暑いですね` | 3 | 0 | 0 | kanji vs kana, same word |
| `音楽を聞く` / `音楽を聴く` | 1 | 0 | 0 | a different kanji for the same word |
| `りんご` / `リンゴ` | 3 | 0 | 0 | hiragana vs katakana |
| `機関` / `期間` | 2 | 2 | 0 | different words with the same sound |
| `橋を渡る` / `箸を渡る` | 1 | 1 | 0 | different words with the same sound |
| `にほん` / `にっぽん` | 2 | 2 | 2 | a different pronunciation |
| `今日は晴れ` / `今日は雨` | 2 | 2 | 2 | a different word |

## Install

Requires Python 3.10 or newer.

```bash
uv add "jacer @ git+https://github.com/third-intelligence/jacer@v1.2.0"
# or
pip install "jacer @ git+https://github.com/third-intelligence/jacer@v1.2.0"
```

## Use

```python
import jacer

# Corpus CER (total edits / total reference characters). The metric defaults
# to "cer_strict", the primary metric.
jacer.cer(references, hypotheses)
jacer.cer(references, hypotheses, "cer_flex")

# Several metrics at once return a dict keyed by metric
refs = ["よろしくお願いします", "会議は3時からです", "機関の名前"]
hyps = ["よろしくおねがいします", "かいぎは3:00からです", "期間の名前"]
jacer.cer(refs, hyps, jacer.METRICS)
# {'cer_strict': 0.2917, 'cer_flex': 0.0833, 'cer_kana': 0.0}
# (rounded to 4 decimal places here; the functions return unrounded floats)

# Errors by type, for one pair (two strings) or a corpus (two lists)
c = jacer.error_counts("今日は良い天気です", "今日は天気でした")
c.substitutions, c.deletions, c.insertions, c.reference_chars   # (1, 2, 1, 9)
c.errors, c.cer                                                 # (4, 0.444...)

# Scoring in batches (validation during training, several workers, ...):
# counts add up with +, so count each batch, sum the counts, and take .cer
# once at the end.
total = jacer.ErrorCounts()
for batch_refs, batch_hyps in batches:
    total += jacer.error_counts(batch_refs, batch_hyps)
total.cer   # identical to jacer.cer(all_refs, all_hyps)

# The exact text a metric compares, for error analysis
jacer.normalize_pair("12時半に集合。", "12:30に集合")
# ('12時半に集合', '12時半に集合')
```

Corpus CER is the total number of errors over all utterances divided by the total number of reference characters (a micro-average). A reference that normalizes to empty is skipped, because CER is undefined for it; `cer` returns `None` if no pair is left.

### User dictionary for cer_kana (optional)

OpenJTalk spells out Latin names it does not know letter by letter (`Siri` becomes エスアイアールアイ). A user dictionary in MeCab/OpenJTalk CSV format adds readings for such names:

```python
jacer.load_user_dict("my_dict.csv")   # applies to every cer_kana call after it
jacer.unload_user_dict()               # back to OpenJTalk's own dictionary
```

See [examples/user_dict.csv](examples/user_dict.csv) for the format (two example entries: Siri and OpenAI). OpenJTalk converts ASCII to full-width before looking words up, so write Latin surfaces in full-width (`Ｓｉｒｉ`); a half-width entry never matches. No user dictionary is loaded by default.

## Versioning

A release that changes any score bumps the minor version or higher (1.2.0 → 1.3.0). A release that changes no score, such as a bug fix or a new API, bumps only the patch version (1.2.0 → 1.2.1). `jacer.METRICS_VERSION` (`"v1.2"`) names the scoring definition, and every `1.2.x` release scores by the same definition. To keep numbers comparable, install a fixed version.

Tokenization, reading and normalization depend on dictionaries and tables shipped by other packages, and a different build of any of them is a different metric. unidic-lite, fugashi, pyopenjtalk-plus, sudachipy, sudachidict-core and neologdn are therefore pinned to exact versions.

## Tests

`tests/test_metrics.py` holds the specification table: which pairs each metric counts as correct. `tests/golden/` pins the exact text each metric compares for 141 edge cases. Run both with:

```bash
uv run pytest
```

## Acknowledgements

jacer builds on the work of the following projects, and we thank their developers and maintainers.

- [UniDic](https://clrd.ninjal.ac.jp/unidic/), [MeCab](https://taku910.github.io/mecab/)
- [fugashi](https://github.com/polm/fugashi), [unidic-lite](https://github.com/polm/unidic-lite)
- [Open JTalk](https://open-jtalk.sourceforge.net/) and its dictionary (NAIST-jdic and others)
- [pyopenjtalk](https://github.com/r9y9/pyopenjtalk), [pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus)
- [Sudachi](https://github.com/WorksApplications/sudachi.rs), [SudachiDict](https://github.com/WorksApplications/SudachiDict)
- [neologdn](https://github.com/ikegami-yukino/neologdn)
- [JiWER](https://github.com/jitsi/jiwer)

## License

Apache License 2.0; see [LICENSE](LICENSE).

jacer bundles no third-party code or data. At runtime it uses the dictionaries its dependencies ship, each under its own license:

| dependency | license | provides |
|---|---|---|
| fugashi | MIT (bundled MeCab: BSD-3-Clause) | MeCab tagger |
| unidic-lite | MIT; UniDic 2.1.2 data: BSD-3-Clause, GPL or LGPL, at the user's choice | tagging dictionary |
| pyopenjtalk-plus | MIT; OpenJTalk and its dictionary (NAIST-jdic, UniDic): BSD-3-Clause | G2P reading |
| sudachipy, sudachidict-core | Apache-2.0 | reading correction inside pyopenjtalk-plus |
| neologdn | Apache-2.0 | text normalization |
| jiwer (+ rapidfuzz MIT, click BSD-3-Clause) | Apache-2.0 | edit distance |
