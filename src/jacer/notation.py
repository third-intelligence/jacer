"""Notation read aloud as words, matched to the reference's format.

The hypothesis is rewritten into the REFERENCE's notation wherever the two
write the same thing differently, under every metric. The reference is never
rewritten, so its length -- the CER denominator -- is its own:

  case      apple / Apple, IPHONE / iPhone
  time      12:00 / 12時, 9:05 / 9時5分, 12:30 / 12時30分 / 12時半
  currency  $100 / 100ドル, ¥500 / 500円
  &         A&B / AアンドB
  units     100% / 100パーセント, 5km / 5キロメートル / 5キロ, 30℃ / 30度
  ranges    3〜5 / 3から5
  fractions 1/2 / 2分の1
  dates     10/1 / 10月1日, 2026/10/1 / 2026年10月1日
  decimals  2.5 / 二点五

Each expression is reduced to one or more keys -- ("time", 12, 30, 0),
("money", "ドル", "100"), ("unit", "5", "km"), ("and",) -- found in both texts,
and a hypothesis expression takes the reference's text for the first of its
keys the reference also has. Matching by key rather than position keeps this
independent of alignment. A notation that is ambiguous carries several keys
(キロ: km or kg; 10/1: a date or a fraction), and the reference decides.

Matching runs in two passes: quantities (times, amounts, units, &) first, then
number forms (ranges, fractions, dates, decimals), so 十から十五パーセント against
10から15% first takes 15% for its unit and then 10から15 for its range. Number
forms are scoped to numbers: から or a slash alone is never rewritten. Units
come from the table in `units`. Currency symbols and & have no dictionary
reading, so they are a table here. Math operators (+ = ×) are deliberately not
matched: their reading depends on context.
"""

from __future__ import annotations

import re
import unicodedata

from jacer import units
from jacer.numerals import KANJI_DIGIT, NUMERAL_PATTERN, numeral_value

_CURRENCY = {"$": "ドル", "¥": "円", "€": "ユーロ", "£": "ポンド", "₩": "ウォン"}
_AMP_RE = re.compile(r"[&＆]|アンド")

_NUM = NUMERAL_PATTERN
_SYM_TIME_RE = re.compile(r"(?<![\d:：])(\d{1,2})[:：]([0-5]\d)(?:[:：]([0-5]\d))?(?![\d:：])")
_WORD_TIME_RE = re.compile(rf"({_NUM})時(?!間)(?:({_NUM})分|(半))?(?:({_NUM})秒)?")  # 3時間 is a duration
_SYM_MONEY_RE = re.compile(r"([" + re.escape("".join(_CURRENCY)) + rf"＄￥])\s?({_NUM})")
_WORD_MONEY_RE = re.compile(rf"({_NUM})(" + "|".join(map(re.escape, _CURRENCY.values())) + ")")


def number_key(text: str) -> str | None:
    """A number's value as a string (三万五千 / 35,000 / 3万5000 -> "35000",
    2.1 -> "2.1"), or None if `text` is not a number."""
    s = unicodedata.normalize("NFKC", text).replace(",", "")
    if re.fullmatch(r"\d+\.\d+", s):
        return s
    v = numeral_value(s)
    return None if v is None else str(v)


def _expressions(text: str) -> list[tuple[int, int, tuple]]:
    """(start, end, key) of every time, amount and & in `text`."""
    found = []
    for m in _SYM_TIME_RE.finditer(text):
        found.append((m.start(), m.end(), ("time", int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))))
    for m in _WORD_TIME_RE.finditer(text):
        h = number_key(m.group(1))
        mi = "30" if m.group(3) else (number_key(m.group(2)) if m.group(2) else "0")
        s = number_key(m.group(4)) if m.group(4) else "0"
        if h and mi and s and "." not in h + mi + s:
            found.append((m.start(), m.end(), ("time", int(h), int(mi), int(s))))
    for m in _SYM_MONEY_RE.finditer(text):
        v = number_key(m.group(2))
        if v:
            found.append((m.start(), m.end(), ("money", _CURRENCY[unicodedata.normalize("NFKC", m.group(1))], v)))
    for m in _WORD_MONEY_RE.finditer(text):
        v = number_key(m.group(1))
        if v:
            found.append((m.start(), m.end(), ("money", m.group(2), v)))
    for m in _AMP_RE.finditer(text):
        found.append((m.start(), m.end(), ("and",)))
    return found


def _non_overlapping(expr: list[tuple[int, int, tuple]]) -> list[tuple[int, int, tuple]]:
    out, end = [], -1
    for e in sorted(expr, key=lambda e: (e[0], -(e[1] - e[0]))):  # leftmost, then longest
        if e[0] >= end:
            out.append(e)
            end = e[1]
    return out


_KANJI_DIGITS = "".join(KANJI_DIGIT)
_NUMD = rf"(?:{_NUM}(?:点[{_KANJI_DIGITS}0-9０-９]+)?)"
_QTY = rf"(?:{_NUMD}|何|数|幾)"  # 何キロ, 数キロ
_QUANTITY_WORDS = ("何", "数", "幾")

_SYM_UNIT_RE = re.compile(
    rf"({_QTY})\s?(°[CF]?|[%％℀-⅏㎀-㏿]|[A-Za-zＡ-Ｚａ-ｚμµ]{{1,5}}[23²³]?)(?![A-Za-zＡ-Ｚａ-ｚ])")
_WORD_UNIT_RE = re.compile(
    rf"({_QTY})(" + "|".join(map(re.escape, sorted(units.WORDS, key=len, reverse=True))) + ")")
_SYM_RANGE_RE = re.compile(rf"({_NUMD})\s?[〜~～\-－–—]\s?({_NUMD})")
_WORD_RANGE_RE = re.compile(rf"({_NUMD})から({_NUMD})")
_SLASH_RE = re.compile(r"(?<![\d/／])([0-9０-９]+)[/／]([0-9０-９]+)(?:[/／]([0-9０-９]+))?(?![\d/／])")
_WORD_FRAC_RE = re.compile(rf"({_NUM})分の({_NUM})")
_WORD_DATE3_RE = re.compile(rf"({_NUM})年({_NUM})月({_NUM})日")
_WORD_DATE2_RE = re.compile(rf"({_NUM})月({_NUM})日")
_SYM_DEC_RE = re.compile(r"(?<![\d.．])([0-9０-９]+[.．][0-9０-９]+)(?![\d.．])")
_WORD_DEC_RE = re.compile(rf"({_NUM})点([{_KANJI_DIGITS}0-9０-９]+)")


def value_key(text: str) -> str | None:
    """`number_key`, plus kanji decimals (二点五 -> "2.5") and the quantity
    words 何 / 数 / 幾, which key as themselves."""
    if text in _QUANTITY_WORDS:
        return text
    s = unicodedata.normalize("NFKC", text)
    if "点" in s:
        whole, _, frac = s.partition("点")
        w = number_key(whole)
        digits = "".join(str(KANJI_DIGIT[c]) if c in KANJI_DIGIT else c for c in frac)
        return f"{w}.{digits}" if w is not None and "." not in w and digits.isdigit() else None
    return number_key(s)


def _int_key(text: str) -> int | None:
    v = number_key(text)
    return None if v is None or "." in v else int(v)


def _date_keys(*parts: int | None) -> tuple:
    if None in parts:
        return ()
    *year, month, day = parts
    return (("date", *year, month, day),) if 1 <= month <= 12 and 1 <= day <= 31 else ()


def _quantity_expressions(text: str) -> list[tuple[int, int, tuple]]:
    """(start, end, keys) of times, amounts, measurements and &, keys in
    priority order -- the first pass."""
    found = [(s, e, (k,)) for s, e, k in _expressions(text)]
    for m in _SYM_UNIT_RE.finditer(text):
        v = value_key(m.group(1))
        ids = units.unit_ids(unicodedata.normalize("NFKC", m.group(2)))
        if v and ids:
            found.append((m.start(), m.end(), tuple(("unit", v, i) for i in sorted(ids))))
    for m in _WORD_UNIT_RE.finditer(text):
        v = value_key(m.group(1))
        if v:
            found.append((m.start(), m.end(), tuple(("unit", v, i) for i in sorted(units.word_unit_ids(m.group(2))))))
    return [f for f in found if f[2]]


def _number_form_expressions(text: str) -> list[tuple[int, int, tuple]]:
    """(start, end, keys) of ranges, fractions, dates and decimals -- the second
    pass, run on the hypothesis after the first, so 十から十五パーセント against
    10から15% first takes 15% for its unit and then 10から15 for its range."""
    found = []
    for rx in (_SYM_RANGE_RE, _WORD_RANGE_RE):
        for m in rx.finditer(text):
            a, b = value_key(m.group(1)), value_key(m.group(2))
            if a and b:
                found.append((m.start(), m.end(), (("range", a, b),)))
    for m in _SLASH_RE.finditer(text):
        a, b, c = (_int_key(g) if g else None for g in m.groups())
        keys = _date_keys(a, b, c) if c is not None else (("frac", a, b), *_date_keys(a, b))
        found.append((m.start(), m.end(), keys))
    for m in _WORD_FRAC_RE.finditer(text):
        den, num = _int_key(m.group(1)), _int_key(m.group(2))
        if den is not None and num is not None:
            found.append((m.start(), m.end(), (("frac", num, den),)))
    for rx in (_WORD_DATE3_RE, _WORD_DATE2_RE):
        for m in rx.finditer(text):
            keys = _date_keys(*(_int_key(g) for g in m.groups()))
            if keys:
                found.append((m.start(), m.end(), keys))
    for m in _SYM_DEC_RE.finditer(text):
        found.append((m.start(), m.end(), (("dec", unicodedata.normalize("NFKC", m.group(1))),)))
    for m in _WORD_DEC_RE.finditer(text):
        v = value_key(m.group(0))
        if v:
            found.append((m.start(), m.end(), (("dec", v),)))
    return [f for f in found if f[2]]


_LATIN_WORD_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]+")


def _latin_key(word: str) -> str:
    return unicodedata.normalize("NFKC", word).casefold()


def match_reference_case(reference: str, hypothesis: str) -> str:
    """A Latin word in the hypothesis takes the reference's casing when the two
    are the same word (apple / Apple, IPHONE / iPhone). Rewriting rather than
    lowercasing both keeps the casing OpenJTalk needs to read a name
    (YouTube is ユーチューブ, youtube is spelled out)."""
    ref_words = {}
    for m in _LATIN_WORD_RE.finditer(reference):
        ref_words.setdefault(_latin_key(m.group()), m.group())
    return _LATIN_WORD_RE.sub(lambda m: ref_words.get(_latin_key(m.group()), m.group()), hypothesis)


def _match_pass(reference: str, hypothesis: str, expressions) -> str:
    """Each hypothesis expression takes the reference's text for the first of
    its keys the reference also has."""
    ref_text: dict[tuple, str] = {}
    for s, e, keys in _non_overlapping(expressions(reference)):
        for k in keys:
            ref_text.setdefault(k, reference[s:e])
    out, pos = [], 0
    for s, e, keys in _non_overlapping(expressions(hypothesis)):
        hit = next((k for k in keys if k in ref_text), None)
        if hit is not None:
            out.append(hypothesis[pos:s] + ref_text[hit])
            pos = e
    out.append(hypothesis[pos:])
    return "".join(out)


def match_reference_notation(reference: str, hypothesis: str) -> str:
    """The hypothesis with Latin words in the reference's casing, then
    quantities (times, amounts, units, &) and then number forms
    (ranges, fractions, dates, decimals) take the reference's notation."""
    hypothesis = match_reference_case(reference, hypothesis)
    hypothesis = _match_pass(reference, hypothesis, _quantity_expressions)
    return _match_pass(reference, hypothesis, _number_form_expressions)


def times_as_words(text: str) -> str:
    """Clock times written as the words they are read as (6:00 -> 6時,
    12:30 -> 12時30分, 9:05:10 -> 9時5分10秒), for cer_kana: OpenJTalk
    reads 6:00 as ロク：ゼロゼロ, colon included. Applied to both texts after the
    hypothesis has taken the reference's notation, so it changes how a time is
    read, never whether it matches. A ratio (3:2) is not a time."""
    def words(m: re.Match) -> str:
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        return f"{h}時" + (f"{mi}分" if mi else "") + (f"{s}秒" if s else "")
    return _SYM_TIME_RE.sub(words, text)
