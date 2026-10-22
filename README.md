# jacer

日本語 | [English](README.en.md)

表記揺れを考慮した日本語音声認識のための文字誤り率（CER）評価ライブラリです。

## 背景

音声認識の精度は、一般に正解文と認識結果を比較した誤り率で評価します。日本語では単語の区切りが曖昧なため、文字単位の誤り率（CER: Character Error Rate）が使われます。CER は、認識結果を正解文に一致させるために必要な文字の置換（Substitution）・削除（Deletion）・挿入（Insertion）の数を、正解文の文字数（N）で割ることで計算されます。

$$
\mathrm{CER} = \frac{S + D + I}{N}
$$

日本語では、同じ言葉を複数の形で表記することが可能です。例えば、数字は漢数字でも算用数字でも書くことができ、単位や時刻の書き方も様々です。また送り仮名の書き方も複数あれば、同じ語を漢字でも仮名でも書くことができます。そのため、モデルが出力した文字列をそのまま比較して CER を計算すると、こうした表記の違いまで誤りとして計算してしまい、モデルの認識性能を正しく測ることが難しくなってしまいます。

例えば、次の2つの文は同じ発話をどちらも正しく書き起こしたものです。

- 正解文：`明日の三時半に二十キロの荷物が届くので、受け取ってください。`
- 認識結果：`明日の3:30に20kgの荷物が届くので受取ってください`

しかし文字列をそのまま比較すると、時刻（「三時半」と「3:30」）で4文字、数字と単位（「二十キロ」と「20kg」）で4文字、送り仮名（「受け取って」と「受取って」）で1文字、句読点で2文字が誤りとされ、30文字中11文字の誤りで CER は約37%と計算されます。

jacer は、認識結果と正解文を比較する前に表記の違いを揃える正規化を施します。これにより、数字・単位・時刻の表記、送り仮名、全角・半角や句読点の違いは誤りとして計算されません。上の例では、認識結果の「3:30」「20kg」「受取って」がそれぞれ正解文の表記に揃えられ、句読点も取り除かれて CER は0%になります。

## 正規化

正規化の詳細は [docs/metrics.md](docs/metrics.md) に記載していますが、主に以下のような表記揺れを解消しています。

| | 正解文 / 認識結果 |
|---|---|
| 全角・半角、句読点、空白 | `ＡＢＣ` / `ABC`、`こんにちは。` / `こんにちは` |
| 数字 | `三人` / `3人`、`二〇二六年` / `2026年`、`3万5000円` / `35,000円` |
| 単位 | `5キロ` / `5km`、`50パーセント` / `50%` |
| 時刻・金額 | `12時半` / `12:30`、`100ドル` / `$100` |
| 英字の大文字・小文字 | `iPhone` / `iphone` |
| 送り仮名 | `申し込む` / `申込む` |
| 細かな表記の慣習 | `3ヶ月` / `3か月`、`コンピューター` / `コンピュータ` |
| 括弧内の注記 | `そうですね(笑)` / `そうですね` |

## 3つの指標

jacer では、上記の正規化に加えて、正解として認識する許容範囲を細分化した3つの CER 指標、CER strict・flex・kana を提供しています。各指標の許容範囲は次のとおりです。

- **CER strict**（`cer_strict`、主指標）：漢字と仮名の使い分けまで正解文と一致しているかを測ります。例えば `今日は綺麗な天気です` と `きょうはきれいなてんきです` の場合では誤りになります。
- **CER flex**（`cer_flex`）：漢字と仮名の使い分けは問わず、正しい語を書き起こせているかを測ります。上のひらがなの例は正解になりますが、`機械学習` を `機会学習` と書くような同音異義語の取り違えは誤りになります。
- **CER kana**（`cer_kana`）：読み（カタカナ）に変換して比較し、正しい音を聞き取れているかを測ります。`機械学習` と `機会学習` は読みが同じなので、正解になります。読みの推定には OpenJTalk を使うため、その読みの誤りもそのまま反映されます。

これらの3つの指標を併せて確認することで、モデルの誤りが音の聞き取り（kana）、語の選択（flex）、漢字と仮名の使い分け（strict）のどの段階で起きているのかまで切り分けて評価することができます。

### 指標によって扱いが異なるもの

各組の誤り数（strict / flex / kana）:

| 正解文 / 認識結果 | strict | flex | kana | 理由 |
|---|---|---|---|---|
| `よろしくお願いします` / `よろしくおねがいします` | 2 | 0 | 0 | 同じ語の漢字と仮名 |
| `会議に参加します` / `かいぎにさんかします` | 6 | 0 | 0 | 同じ語の漢字と仮名 |
| `今日は暑いですね` / `きょうは暑いですね` | 3 | 0 | 0 | 同じ語の漢字と仮名 |
| `音楽を聞く` / `音楽を聴く` | 1 | 0 | 0 | 同じ語の異なる漢字 |
| `りんご` / `リンゴ` | 3 | 0 | 0 | ひらがなとカタカナ |
| `機関` / `期間` | 2 | 2 | 0 | 同音異義語 |
| `橋を渡る` / `箸を渡る` | 1 | 1 | 0 | 同音異義語 |
| `にほん` / `にっぽん` | 2 | 2 | 2 | 発音が異なる |
| `今日は晴れ` / `今日は雨` | 2 | 2 | 2 | 別の語 |

## インストール

Python 3.10 以上が必要です。

```bash
uv add "jacer @ git+https://github.com/third-intelligence/jacer@v1.2.0"
# または
pip install "jacer @ git+https://github.com/third-intelligence/jacer@v1.2.0"
```

## 使い方

```python
import jacer

# コーパス全体の CER（誤り数の合計 / 正解文の文字数の合計）
# 指標を省略すると主指標の "cer_strict" になります。
jacer.cer(references, hypotheses)
jacer.cer(references, hypotheses, "cer_flex")

# 複数の指標をまとめて計算すると、指標名をキーとする辞書が返ります
refs = ["よろしくお願いします", "会議は3時からです", "機関の名前"]
hyps = ["よろしくおねがいします", "かいぎは3:00からです", "期間の名前"]
jacer.cer(refs, hyps, jacer.METRICS)
# {'cer_strict': 0.2917, 'cer_flex': 0.0833, 'cer_kana': 0.0}
# （ここでは小数点以下4桁に丸めて表示。実際の戻り値は丸めていない浮動小数点数）

# 誤りを種類別（置換・削除・挿入）に数えます。
# 1サンプル（string 2つ）でもコーパス全体（リスト2つ）でも使えます
c = jacer.error_counts("今日は良い天気です", "今日は天気でした")
c.substitutions, c.deletions, c.insertions, c.reference_chars   # (1, 2, 1, 9)
c.errors, c.cer                                                 # (4, 0.444...)

# バッチ単位での計算（学習中の検証や、複数ワーカーでの並列処理など）:
# 誤り数は + で足し合わせられるので、バッチごとに数えて合計し、
# 最後に一度だけ .cer を求めます。
total = jacer.ErrorCounts()
for batch_refs, batch_hyps in batches:
    total += jacer.error_counts(batch_refs, batch_hyps)
total.cer   # jacer.cer(all_refs, all_hyps) と同じ

# 指標が実際に比較するテキスト（誤り分析用）
jacer.normalize_pair("12時半に集合。", "12:30に集合")
# ('12時半に集合', '12時半に集合')
```

コーパスの CER は、すべての発話の誤りの数の合計を、正解文の文字数の合計で割って求めます（マイクロ平均）。
正規化すると空になる正解文は、CER が定義できないため計算から除外します。残る組がなければ `cer` は `None` を返します。

### cer_kana 用のユーザー辞書（任意）

OpenJTalk は辞書にない英字の固有名詞をアルファベット読みにします（例えば `Siri` はエスアイアールアイ）。MeCab / OpenJTalk 形式のユーザー辞書（CSV）を読み込むと、こうした語の読みを追加できます。

```python
jacer.load_user_dict("my_dict.csv")   # 以降のすべての cer_kana に適用
jacer.unload_user_dict()               # OpenJTalk 標準の辞書に戻す
```

形式は [examples/user_dict.csv](examples/user_dict.csv) を参照してください（Siri、OpenAI の2項目を例として追加しています）。OpenJTalk は辞書を引く前に英数字を全角に変換するため、英字の表層形は全角（`Ｓｉｒｉ`）で書いてください（半角で書いた項目は一致しません）。デフォルトではユーザー辞書は読み込まれません。

## バージョンについて

スコアが1つでも変わるリリースでは、バージョンの2桁目以上を変更します（例：1.2.0 → 1.3.0）。不具合の修正や API の追加など、スコアが変わらないリリースでは3桁目だけを変更します（例：1.2.0 → 1.2.1）。採点の定義は `jacer.METRICS_VERSION`（`"v1.2"`）で確認でき、`1.2.x` のリリースはすべて同じ定義で採点します。数値を比較可能に保つには、バージョンを固定してインストールしてください。

形態素解析・読み推定・正規化は、他のパッケージが提供する辞書や変換表に依存します。いずれかの版が変われば別の指標になるため、unidic-lite、fugashi、pyopenjtalk-plus、sudachipy、sudachidict-core、neologdn の版は厳密に固定しています。

## テスト

`tests/test_metrics.py` には、各指標がどの組を正解とするかを定めた仕様の表があります。`tests/golden/` には、141のエッジケースについて各指標が実際に比較するテキストを固定しています。どちらも次のコマンドで実行できます。

```bash
uv run pytest
```

## 謝辞

jacer は次のプロジェクトの成果の上に成り立っています。開発者とメンテナーの皆さんに感謝の意を表します。

- [UniDic](https://clrd.ninjal.ac.jp/unidic/)、[MeCab](https://taku910.github.io/mecab/)
- [fugashi](https://github.com/polm/fugashi)、[unidic-lite](https://github.com/polm/unidic-lite)
- [Open JTalk](https://open-jtalk.sourceforge.net/) とその辞書（NAIST-jdic ほか）
- [pyopenjtalk](https://github.com/r9y9/pyopenjtalk)、[pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus)
- [Sudachi](https://github.com/WorksApplications/sudachi.rs)、[SudachiDict](https://github.com/WorksApplications/SudachiDict)
- [neologdn](https://github.com/ikegami-yukino/neologdn)
- [JiWER](https://github.com/jitsi/jiwer)

## ライセンス

Apache License 2.0 です。[LICENSE](LICENSE) を参照してください。

jacer は第三者のコードやデータを同梱していません。実行時には依存パッケージが提供する辞書を使用し、それぞれに各自のライセンスが適用されます。

| 依存パッケージ | ライセンス | 用途 |
|---|---|---|
| fugashi | MIT（同梱の MeCab: BSD-3-Clause） | MeCab による形態素解析 |
| unidic-lite | MIT。UniDic 2.1.2 のデータは BSD-3-Clause・GPL・LGPL から選択 | 形態素解析用の辞書 |
| pyopenjtalk-plus | MIT。OpenJTalk とその辞書（NAIST-jdic、UniDic）: BSD-3-Clause | 読み推定（G2P） |
| sudachipy, sudachidict-core | Apache-2.0 | pyopenjtalk-plus 内での読みの補正 |
| neologdn | Apache-2.0 | テキストの正規化 |
| jiwer（+ rapidfuzz: MIT、click: BSD-3-Clause） | Apache-2.0 | 編集距離の計算 |
