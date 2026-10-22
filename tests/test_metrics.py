from pathlib import Path

import jiwer
import pytest

import jacer

from jacer import METRICS, cer, error_counts, normalize_pair

# The table below IS the specification: each row says which metrics treat the
# hypothesis as correct. "sfk" = strict, flex and kana all score 0 edits;
# "" = an error under every metric.

V12_SPEC = [
    # clipped and table units (both directions, and a quantity word)
    ("5キロ走った", "5km走った", "sfk"), ("体重60キロ", "体重60kg", "sfk"), ("何キロありますか", "何kmありますか", "sfk"),
    ("5km", "5キロ", "sfk"), ("10センチ", "10cm", "sfk"), ("64ギガ", "64GB", "sfk"), ("100メガ", "100MB", "sfk"),
    ("5メートル", "5m", "sfk"), ("500グラム", "500g", "sfk"), ("2リットル", "2L", "sfk"), ("50ヘルツ", "50Hz", "sfk"),
    ("100ワット", "100W", "sfk"), ("面積は30平方メートル", "面積は30㎡", "sfk"), ("30度", "30℃", "sfk"),
    # numeric ranges, fractions, dates, kanji decimals
    ("3から5人", "3〜5人", "sfk"), ("3〜5人", "3から5人", "sfk"), ("2分の1", "1/2", "sfk"), ("10月1日", "10/1", "sfk"),
    ("2026年10月1日", "2026/10/1", "sfk"), ("2.5倍", "二点五倍", "sfk"),
    # numbers in words
    ("一人で", "1人で", "sfk"), ("ひとつ", "一つ", "fk"), ("ひとりで", "1人で", "fk"), ("二十歳", "20歳", "sfk"),
    # same-word notation conventions
    ("3ヶ月", "3か月", "sfk"), ("3ヶ月", "3カ月", "sfk"), ("3ヶ所", "3か所", "sfk"), ("時々", "時時", "sfk"),
    ("コンピューター", "コンピュータ", "sfk"), ("バイオリン", "ヴァイオリン", "sfk"), ("ウイルス", "ウィルス", "sfk"),
    # characters: case, symbols, brackets, invisible characters
    ("Apple", "apple", "sfk"), ("iPhone", "IPHONE", "sfk"), ("こんにちは", "“こんにちは”", "sfk"),
    ("こんにちは", "♪こんにちは♪", "sfk"), ("注意", "※注意", "sfk"), ("はい", "はい：", "sfk"),
    ("そうですね", "そうですね(笑)", "sfk"), ("そうですね", "（拍手）そうですね", "sfk"), ("映画", "『映画』", "sfk"),
    ("彼は「はい」と言った", "彼ははいと言った", "sfk"), ("こんにちは", "こんに​ちは", "sfk"),
    # brackets whose content the other text also says: only the brackets go
    ("離島では使えません 確認しましょう", "離島では使えません(確認しましょう)。", "sfk"),
    ("昨年夏にオープンしたセンターです。", "[昨年夏にオープンしたセンターです]", "sfk"),
    ("起こるのである（故に表現作用的である）。", "起こるのである、故に表現作用的である。", "sfk"),
    ("ポンドfkpで", "ポンド（FKP）で", "sfk"),
    # found by validation on model output
    ("10から15%ぐらい", "十から十五パーセントぐらい", "sfk"), ("合計、１、０００名", "合計千名", "sfk"),
    ("トップスプリンター", "トップスリンダ", ""), ("千年以上も前から", "000年以上前から", ""),
    ("三、四週間", "34週間", ""),
    ("電話は090-1234-5678です", "電話は09012345678です", "sfk"), ("090-1234-5678", "090-1234-5679", ""),
    # digit strings are codes, compared digit by digit, never as a value
    ("〇一〇一", "0101", "sfk"), ("零一一一", "0111", "sfk"), ("0110", "110", ""),
    # kana reads the flex-aligned pair
    ("日本", "ニッポン", "fk"), ("機関", "期間", "k"),
    # still errors
    ("5キロ走った", "6km走った", ""), ("3から5人", "3〜6人", ""), ("2分の1", "2/3", ""), ("10月1日", "10/2", ""),
    ("一人で", "2人で", ""), ("ひとつ", "二つ", ""), ("2.5倍", "二点六倍", ""), ("東京から大阪", "東京〜大阪", ""),
    ("新曲のMV", "新曲のメガボルト", ""), ("比は3対2", "比は3:2", ""), ("1プラス1", "1+1", ""), ("にほん", "にっぽん", ""),
    ("Apple", "Apply", ""), ("コンピューター", "コンピュート", ""), ("僕", "ぼく", "fk"),
    # out of scope (documented): Latin vs katakana spelling of a word, in strict and flex
    ("アップル", "Apple", "k"),
]


@pytest.mark.parametrize("ref,hyp,forgiven", V12_SPEC)
def test_spec(ref, hyp, forgiven):
    for flag, metric in (("s", "cer_strict"), ("f", "cer_flex"), ("k", "cer_kana")):
        edits = error_counts(ref, hyp, metric).errors
        assert (edits == 0) == (flag in forgiven), (metric, ref, hyp, edits)


def test_strict_flex_kana_are_nested():
    # Every pair strict forgives, flex forgives too; every pair flex forgives,
    # kana forgives too (kana reads the flex-aligned pair).
    for ref, hyp, _ in V12_SPEC:
        s, f, k = (error_counts(ref, hyp, m).errors for m in METRICS)
        assert (s == 0) <= (f == 0) <= (k == 0), (ref, hyp, s, f, k)


def test_script_choices():
    for ref, hyp in [("私は学生です", "わたしは学生です"), ("綺麗な花", "きれいな花"), ("聞く", "聴く"),
                     ("ねこがいる", "ネコがいる"), ("日本に行く", "にっぽんに行く"), ("美しい花です", "うつくしい花です")]:
        assert error_counts(ref, hyp, "cer_strict").errors > 0, (ref, hyp)
        assert error_counts(ref, hyp, "cer_flex").errors == 0, (ref, hyp)
    for ref, hyp in [("申し込む", "申込む"), ("彼はそれを断る", "彼はそれを断わる"), ("取り扱い", "取扱い")]:
        assert error_counts(ref, hyp, "cer_strict").errors == 0, (ref, hyp)
    # kana spellings of different pronunciations each commit to what was said
    for ref, hyp in [("にほんに行く", "にっぽんに行く"), ("わたしは学生です", "わたくしは学生です")]:
        assert error_counts(ref, hyp, "cer_flex").errors > 0, (ref, hyp)


def test_reference_is_never_rewritten():
    for metric in ("cer_strict", "cer_flex"):
        assert normalize_pair("百八十五センチの猫", "185センチの猫", metric) == ("百八十五センチの猫",) * 2
        assert normalize_pair("売上は23億円", "売上は2300000000円", metric) == ("売上は23億円",) * 2
        assert normalize_pair("成功率は50%", "成功率は50パーセント", metric) == ("成功率は50%",) * 2
        assert normalize_pair("7時半から", "7:30から", metric) == ("7時半から",) * 2


def test_wrong_number_is_scored_in_the_reference_style():
    # 1888 against 千八百八十九: written as 千八百八十八, one kanji off.
    assert cer(["千八百八十九年"], ["1888年"], "cer_strict") == pytest.approx(1 / 7)
    assert cer(["1889年"], ["千八百八十八年"], "cer_strict") == pytest.approx(1 / 5)
    assert cer(["1万6800円"], ["16900円"], "cer_strict") == pytest.approx(1 / 7)


def test_numerals():
    from jacer.numerals import format_like, numeral_value
    assert numeral_value("百八十五") == 185 and numeral_value("二〇二五") == 2025
    assert numeral_value("一億二千万") == 120_000_000 and numeral_value("3万5000") == 35000
    assert numeral_value("猫") is None
    assert format_like(16800, "1万5000") == "1万6800" and format_like(16800, "15000") == "16800"
    assert format_like(1888, "千八百八十九") == "千八百八十八" and format_like(2026, "二〇二五") == "二〇二六"


def test_differently_segmented_tokens_are_not_rewritten():
    # UniDic splits げっ歯 as げ|っ歯 in one text and げっ|歯 in the other;
    # copying っ歯 over 歯 would produce げっっ歯.
    for metric in ("cer_strict", "cer_flex"):
        _, hyp = normalize_pair("最後に 昆虫 げっ歯類 トカゲ", "最後に昆虫、げっ歯類、トカゲ", metric)
        assert hyp == "最後に昆虫げっ歯類トカゲ", metric


def test_symbols_are_kept_in_the_scored_text():
    assert normalize_pair("マレーシア", "マレ ーシア", "cer_strict") == ("マレーシア", "マレーシア")
    assert normalize_pair("1+1", "1+1", "cer_strict")[0] == "1+1"
    assert error_counts("3.5メートル", "35メートル", "cer_strict").errors > 0


def test_kana_user_dictionary_is_opt_in():
    import jacer
    example = Path(__file__).parents[1] / "examples" / "user_dict.csv"
    pair = ("OpenAIに聞いてみた", "オープンエーアイに聞いてみた")
    assert jacer.scoring_environment()["user_dict"] is None
    assert error_counts(*pair, "cer_kana").errors > 0  # OpenJTalk alone spells OpenAI out
    jacer.load_user_dict(example)
    try:
        assert error_counts(*pair, "cer_kana").errors == 0
        assert error_counts("Appleから新しいSiriがでた", "アップルから新しいシリがでた", "cer_kana").errors == 0
        assert jacer.scoring_environment()["user_dict"]["path"] == str(example.resolve())
    finally:
        jacer.unload_user_dict()
    assert error_counts(*pair, "cer_kana").errors > 0
    assert jacer.scoring_environment()["user_dict"] is None


def test_kana_never_leaves_text_unread():
    # OpenJTalk returns some runs as written; they are re-read in halves.
    from jacer.kana import _UNREAD_RE, _g2p_complete
    out = _g2p_complete("横田家二世絶来展住後前死は迎えられて")
    assert not _UNREAD_RE.search(out) and out.startswith("ヨコタ")


def test_kana_reads_clock_times_as_words():
    ref = "駐車場は、朝の6:00から夜の12:00までです。"
    assert normalize_pair(ref, ref, "cer_kana")[0] == "チューシャジョーワアサノロクジカラヨルノジューニジマデデス"
    for metric in METRICS:
        assert error_counts(ref, "駐車場は朝の6時から夜の12時までです。", metric).errors == 0
    # a wrong time is one reading off, not a colon and two zeros
    assert error_counts("6:00に集合", "7時に集合", "cer_kana").errors <= 2


def test_brackets():
    from jacer.text import drop_bracketed
    assert drop_bracketed("(彼(田中)は)来た") == "来た"      # outermost pair
    assert drop_bracketed("(笑そうですね") == "(笑そうですね"  # unbalanced: nothing deleted
    assert drop_bracketed("3<5かつ6>4") == "3<5かつ6>4"      # a comparison, not a tag
    assert drop_bracketed("「はい」") == "「はい」"            # quotes are not brackets


def test_unit_table():
    from jacer.units import unit_ids, word_unit_ids
    assert unit_ids("km") == unit_ids("KM") == {"km"} and unit_ids("ml") == {"mL"} and unit_ids("KB") == {"kB"}
    assert {"km", "kg"} <= word_unit_ids("キロ") and word_unit_ids("センチ") == {"cm"}
    assert unit_ids("the") == unit_ids("OK") == unit_ids("Web") == frozenset()


def test_error_counts_sum_to_corpus_cer():
    # Sharded scoring: summing per-pair counts reproduces the corpus CER exactly.
    refs = ["私は学生です", "成功率は100%です", "", "7時半に集合", "3.5メートル"]
    hyps = ["わたしは学生です", "成功率は100パーセントです", "余計", "7:30に集合", "35メートル"]
    for metric in METRICS:
        total = sum((error_counts(r, h, metric) for r, h in zip(refs, hyps)), jacer.ErrorCounts())
        assert total == error_counts(refs, hyps, metric) and total.cer == cer(refs, hyps, metric), metric
        assert total.cer == pytest.approx(jiwer.cer(*map(list, zip(*[normalize_pair(r, h, metric)
                                                                  for r, h in zip(refs, hyps) if r]))))


def test_error_types():
    c = error_counts("今日は良い天気です", "今日は天気でした", "cer_strict")
    assert (c.substitutions, c.deletions, c.insertions, c.reference_chars) == (1, 2, 1, 9)  # 良い deleted; です -> でした
    assert c.errors == 4 and c.cer == 4 / 9
    assert error_counts("会議", "会議です", "cer_strict").insertions == 2
    assert error_counts("", "余計", "cer_strict") == jacer.ErrorCounts() and cer([""], ["余計"], "cer_flex") is None


def test_default_metric_and_several_metrics():
    refs, hyps = ["よろしくお願いします", "機関"], ["よろしくおねがいします", "期間"]
    assert cer(refs, hyps) == cer(refs, hyps, "cer_strict")
    assert error_counts(refs[0], hyps[0]) == error_counts(refs[0], hyps[0], "cer_strict")
    assert normalize_pair(refs[0], hyps[0]) == normalize_pair(refs[0], hyps[0], "cer_strict")
    scores = cer(refs, hyps, METRICS)
    assert list(scores) == list(METRICS) and scores == {m: cer(refs, hyps, m) for m in METRICS}
    assert scores["cer_strict"] > scores["cer_flex"] > scores["cer_kana"] == 0
    assert set(error_counts(refs[0], hyps[0], ["cer_flex", "cer_kana"])) == {"cer_flex", "cer_kana"}
    assert set(normalize_pair(refs[0], hyps[0], METRICS)) == set(METRICS)


def test_empty_references_and_bad_input():
    assert cer(["これは", ""], ["これは", "余計"], "cer_strict") == 0.0
    assert cer(["", " "], ["a", "b"], "cer_kana") is None
    with pytest.raises(ValueError):
        cer(["a"], [], "cer_flex")
    with pytest.raises(TypeError):
        error_counts("a", ["a"], "cer_flex")
    with pytest.raises(KeyError):
        normalize_pair("a", "b", "cer")
