# Metric definition (v1.2)

[日本語](metrics.md) | English

The normalization rules jacer applies, in detail.

## 1. Characters and symbols (all three metrics)

- Full-width and half-width forms are treated as the same, and repeated long-vowel marks (`ーー`) and wave dashes are collapsed.
- Latin case is ignored (`Apple` / `apple`, `iPhone` / `IPHONE`).
- Whitespace, punctuation and symbols that are not read aloud (quotation marks, `♪`, `※`, `：` and so on) are removed. `「」` and `『』` count as quotation marks: the marks go, their content stays.
- Symbols that are read aloud are kept: `% & # @ / °`, math symbols (`+ = < > × ÷ ± ~` and so on) and currency signs (`$ ¥ € £ ₩` and so on).
- `.` and `:` are kept only between two digits, so that `3.5` and `35` stay different.
- Brackets (`()` `[]` `{}` `<>` `【】` `〔〕` `〈〉` `《》` `〖〗` `〘〙` `⦅⦆` and their full-width forms) are removed together with their content, as annotations: `(笑)`, `[音楽]`, `<noise>`, ruby readings.
  - Exception: if the content is also spoken in the other text, only the brackets are removed and the content stays.
  - Exception: `<...>` containing a digit is a comparison and is kept (`3<5かつ6>4`).
- Invisible characters such as zero-width spaces are removed.

## 2. Numbers, times and units (all three metrics)

These differences in notation are correct under every metric:

| kind | examples (reference / hypothesis) |
|---|---|
| numbers | `百八十五` / `185`, `二〇二六` / `2026`, `三万五千` / `35000` / `3万5000` / `35,000`, `合計、１、０００名` / `合計千名`, `一人` / `1人` |
| phone numbers and codes | `090-1234-5678` / `09012345678`, `〇一〇一` / `0101` |
| times | `12時` / `12:00`, `9時5分` / `9:05`, `12時半` / `12:30` / `12時30分` |
| money | `100ドル` / `$100`, `500円` / `¥500` |
| `&` | `AアンドB` / `A&B` |
| units | `5メートル` / `5m`, `500グラム` / `500g`, `2リットル` / `2L`, `50ヘルツ` / `50Hz`, `30平方メートル` / `30㎡`, `30度` / `30℃`, `100%` / `100パーセント` |
| shortened units | `5キロ` / `5km`, `体重60キロ` / `体重60kg`, `10センチ` / `10cm`, `64ギガ` / `64GB`, `何キロ` / `何km` |
| ranges | `3から5人` / `3〜5人`, `10から15%` / `十から十五パーセント` |
| fractions | `2分の1` / `1/2` |
| dates | `10月1日` / `10/1`, `2026年10月1日` / `2026/10/1` |
| kanji decimals | `2.5倍` / `二点五倍` |

A notation with more than one meaning takes the meaning that matches the reference: `キロ` can be km or kg, and `10/1` can be a date or a fraction.

A `、` between numbers is a thousands separator when exactly three digits follow it (`１、０００` is 1000); otherwise it separates two numbers. `三、四週間` ("three or four weeks") is not the number 34 but 3 and 4, so `三、四週間` / `3、4週間` is correct.

A number that starts with 0 (`0110`, `〇一〇一`) is a code, compared digit by digit rather than by value: `0110` / `110` is an error.

These are not treated as the same:

- `から` or a slash without numbers on both sides (`東京から大阪` / `東京〜大阪`)
- operators (`1プラス1` / `1+1`)
- ratios (`3対2` / `3:2`)
- Latin abbreviations without a number (the `MV` in `新曲のMV` is not a megavolt)

## 3. How words are written (differs between cer_strict and cer_flex)

Different spellings of the same word are treated as follows:

| reference / hypothesis | cer_strict | cer_flex |
|---|---|---|
| same kanji, different okurigana (`申し込む` / `申込む`, `取り扱い` / `取扱い`, `断る` / `断わる`) | correct | correct |
| counters (`3ヶ月` / `3か月` / `3カ月`, `3ヶ所` / `3か所`) | correct | correct |
| `々` (`時々` / `時時`) | correct | correct |
| katakana spellings of a loanword (`コンピューター` / `コンピュータ`, `バイオリン` / `ヴァイオリン`, `ウイルス` / `ウィルス`) | correct | correct |
| kanji vs kana (`お願い` / `おねがい`, `会議` / `かいぎ`, `今日` / `きょう`, `私` / `わたし`) | error | correct |
| a kanji word and its reading in kana (`日本` / `にほん`, `日本` / `にっぽん`; any reading of a word with several) | error | correct |
| a different kanji for the same word (`聞く` / `聴く`, `分かる` / `解る`) | error | correct |
| hiragana vs katakana (`りんご` / `リンゴ`) | error | correct |
| kana spellings of different pronunciations (`にほん` / `にっぽん`, `わたし` / `わたくし`) | error | error |
| different words with the same sound (`機関` / `期間`) | error | error |

Two katakana spellings of a loanword are correct only when they differ just in the long-vowel mark (`コンピューター` / `コンピュータ`), small vowels (`ウィルス` / `ウイルス`) or `ヴ` versus the `バ` row (`ヴァイオリン` / `バイオリン`).

Numbers written in kana (`ひとり`, `ひとつ`) are a kana spelling too, so `ひとり` / `1人` and `ひとつ` / `一つ` are correct under cer_flex only.

## cer_kana

cer_kana takes the texts as cer_flex processes them, converts both to katakana readings with OpenJTalk, and compares the readings. It accepts everything cer_flex accepts, plus different words with the same sound (`機関` / `期間`).

The readings are OpenJTalk's guesses, so when OpenJTalk misreads a word (one with several readings, a proper noun, a word missing from its dictionary), the misreading counts in the score as well. A user dictionary (`load_user_dict`) can add readings for specific words (`Siri` → シリ).

## Out of scope

| not treated as correct | why |
|---|---|
| paraphrases, synonyms and register (`午後3時` / `15時`, `3割` / `30%`, `半分` / `2分の1`, Japanese era / Western year, `です` / `である`) | what was said is different |
| Latin vs katakana spelling (`Apple` / `アップル`) | not supported yet. cer_kana accepts it only for words whose Latin spelling OpenJTalk can read (`Apple`, `Google`); others (`Siri`, `ChatGPT`) are read letter by letter, so they remain errors |
| old or variant kanji (`髙` / `高`) | often chosen deliberately in names |
