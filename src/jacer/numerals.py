"""Japanese numerals: parsing, and writing a value in a given style.

Shared by the aligner (`ortho`: numbers of equal value take the reference's
spelling) and the notation matcher (`notation`: the number inside a time,
amount or measurement). The digit and unit tables are the single definition
of what counts as a numeral character.
"""

from __future__ import annotations

import unicodedata


KANJI_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
SMALL_UNIT = {"十": 10, "百": 100, "千": 1000}
LARGE_UNIT = {"万": 10**4, "億": 10**8, "兆": 10**12, "京": 10**16}

# One numeral as it appears in text: digits (full- or half-width, with grouping
# commas or a decimal point) and/or kanji numerals -- built from the tables above.
_NUMERAL_CHARS = "0-9０-９" + "".join(KANJI_DIGIT) + "".join(SMALL_UNIT) + "".join(LARGE_UNIT)
NUMERAL_PATTERN = rf"[{_NUMERAL_CHARS}][{_NUMERAL_CHARS},，.．]*"


def _coefficient(digits: str) -> int | None:
    if digits.isascii() and digits.isdigit():
        return int(digits)
    if len(digits) == 1 and digits in KANJI_DIGIT:
        return KANJI_DIGIT[digits]
    return None


def _section_value(sec: str) -> int | None:
    """A number below 10,000: "185", "百八十五", "3千", or a digit-by-digit
    kanji reading such as a year "二〇二五"."""
    if not sec:
        return None
    if sec.isascii() and sec.isdigit():
        return int(sec)
    if all(ch in KANJI_DIGIT for ch in sec):
        return int("".join(str(KANJI_DIGIT[ch]) for ch in sec))
    total, buf = 0, ""
    for ch in sec:
        if ch in SMALL_UNIT:
            k = _coefficient(buf) if buf else 1
            if k is None:
                return None
            total, buf = total + k * SMALL_UNIT[ch], ""
        elif ch in KANJI_DIGIT or (ch.isascii() and ch.isdigit()):
            buf += ch
        else:
            return None
    if buf:
        k = _coefficient(buf)
        if k is None:
            return None
        total += k
    return total


def numeral_value(text: str) -> int | None:
    """Integer value of a numeral written in kanji, digits, or a mix
    (三万五千 / 35,000 / 3万5000 all give 35000), or None if it isn't one."""
    s = unicodedata.normalize("NFKC", text).replace(",", "")
    if not s:
        return None
    total, sec = 0, ""
    for ch in s:
        if ch in LARGE_UNIT:
            k = _section_value(sec) if sec else 1
            if k is None:
                return None
            total, sec = total + k * LARGE_UNIT[ch], ""
        else:
            sec += ch
    if sec:
        k = _section_value(sec)
        if k is None:
            return None
        total += k
    return total


# Value -> kanji digit, for writing numbers (〇 for zero; 零 is only read).
DIGIT_KANJI = {v: k for k, v in KANJI_DIGIT.items() if k != "零"}
_LARGE_DESC = sorted(LARGE_UNIT.items(), key=lambda kv: -kv[1])
_SMALL_DESC = sorted(SMALL_UNIT.items(), key=lambda kv: -kv[1])


def _mixed(value: int) -> str:
    """Digits with 万/億/兆 units, the usual Japanese written form (1万6800)."""
    out = ""
    for unit, base in _LARGE_DESC:
        if value >= base:
            out += f"{value // base}{unit}"
            value %= base
    return out + (str(value) if value or not out else "")


def _kanji_section(n: int) -> str:
    out = ""
    for unit, base in _SMALL_DESC:
        if n >= base:
            d = n // base
            out += ("" if d == 1 else DIGIT_KANJI[d]) + unit
            n %= base
    return out + (DIGIT_KANJI[n] if n else "")


def _kanji(value: int) -> str:
    """Positional kanji numerals (千八百八十九, 一万六千八百)."""
    if value == 0:
        return DIGIT_KANJI[0]
    out = ""
    for unit, base in _LARGE_DESC:
        if value >= base:
            out += _kanji_section(value // base) + unit
            value %= base
    return out + _kanji_section(value)


def format_like(value: int, like: str) -> str:
    """`value` written in the style of the numeral `like`: plain digits,
    digits with 万/億 units, positional kanji, or digit-by-digit kanji (二〇二五)."""
    s = unicodedata.normalize("NFKC", like).replace(",", "")
    if any(c.isascii() and c.isdigit() for c in s):
        return _mixed(value) if any(c in LARGE_UNIT for c in s) else str(value)
    if len(s) > 1 and all(c in KANJI_DIGIT for c in s):
        return "".join(DIGIT_KANJI[int(d)] for d in str(value))
    return _kanji(value)
