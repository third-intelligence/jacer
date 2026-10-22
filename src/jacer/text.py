"""Character-level normalization of Japanese text (no tagging)."""

import unicodedata
from difflib import SequenceMatcher

import neologdn

from jacer.numerals import KANJI_DIGIT, LARGE_UNIT, SMALL_UNIT

# Brackets whose content is deleted with them (annotations: (笑), [音楽],
# <noise>, ruby readings, asides), both widths. 「」 and 『』 are quotation
# marks, not brackets: they go with the punctuation and their content stays.
_BRACKETS = dict(zip("([{<（［｛＜【〔〈《〖〘⦅｟", ")]}>）］｝＞】〕〉》〗〙⦆｠"))
_CLOSERS = frozenset(_BRACKETS.values())
_ANGLE = frozenset("<＜")
_DIGITS = frozenset("0123456789０１２３４５６７８９")

# Punctuation and other symbols (P*, So, Sk) are removed, except these, which are
# read aloud. Math symbols (Sm: + = < > × ~) and currency signs (Sc: $ ¥ €) are
# never removed. All of them stay after `notation` has put them in the
# reference's notation where it can.
_SPOKEN_SYMBOLS = frozenset("%&#@/°")
# Kept only between two digits: a decimal point (3.5) and a time or ratio (3:2).
_DIGIT_JOINERS = frozenset(".:")
# Characters that never carry content: format characters (zero-width space,
# BOM, joiners), combining marks left after NFKC, variation selectors.
_INVISIBLE = frozenset({"Cf", "Mn", "Me", "Cc"})


def _bracket_spans(text: str) -> list[tuple[int, int]]:
    """Outermost balanced bracket pairs. A stray bracket opens or closes
    nothing; <...> holding a digit is a comparison (3<5かつ6>4), not a tag."""
    spans, stack = [], []
    for i, ch in enumerate(text):
        if ch in _BRACKETS:
            stack.append((ch, i))
        elif ch in _CLOSERS and stack and _BRACKETS[stack[-1][0]] == ch:
            opener, start = stack.pop()
            if opener in _ANGLE and any(c in _DIGITS for c in text[start:i]):
                continue
            spans.append((start, i + 1))
    spans.sort()
    outer, end = [], -1
    for s, e in spans:
        if s >= end:  # a span inside an earlier one is already covered
            outer.append((s, e))
            end = e
    return outer


# A bracketed span is spoken content, not an annotation, when at least this
# share of its characters also occurs, in order, in the other text.
_SPOKEN_SHARE = 0.5


def _spoken_in(content: str, other: str) -> bool:
    c, o = normalize(content).casefold(), normalize(other).casefold()
    if not c:
        return False
    matched = sum(b.size for b in SequenceMatcher(None, c, o, autojunk=False).get_matching_blocks())
    return matched >= _SPOKEN_SHARE * len(c)


def drop_bracketed(text: str, other: str | None = None) -> str:
    """Delete each bracketed span (keeping 「」『』, which are quotes). With
    `other`, a span whose content the other text also says is spoken -- a
    model's whole answer wrapped in [...], an aside a reference keeps in
    parentheses -- and only its brackets go; an annotation ((笑), [音楽],
    <noise>) that the other text does not say is deleted with its content."""
    out, pos = [], 0
    for s, e in _bracket_spans(text):
        out.append(text[pos:s])
        if other is not None and _spoken_in(text[s + 1:e - 1], other):
            out.append(text[s + 1:e - 1])
        pos = e
    out.append(text[pos:])
    return "".join(out)


def drop_invisible(text: str) -> str:
    return "".join(ch for ch in text if unicodedata.category(ch) not in _INVISIBLE)


def preclean(reference: str, hypothesis: str) -> tuple[str, str]:
    """Applied to the pair before anything else: invisible characters out (a
    zero-width space splits a word for the tagger), then each text's
    bracketed annotations, judged against the other text."""
    reference, hypothesis = drop_invisible(reference), drop_invisible(hypothesis)
    return drop_bracketed(reference, hypothesis), drop_bracketed(hypothesis, reference)


def _ascii_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


PAUSE = "、"
# List separators that become a pause between numerals; a hyphen joins a
# code (090-1234) and is not one.
_LIST_SEPARATORS = frozenset("、,，・･")
# Text is NFKC-normalized here, so half-width digits suffice. 京 is left out: in
# 東京、三人 it is the capital, not a numeral, and the 、 is not a list pause.
_NUMERAL_CHARS = frozenset("0123456789").union(KANJI_DIGIT, SMALL_UNIT, LARGE_UNIT) - {"京"}


def _between_numerals(out: list[str], nxt: str) -> bool:
    return bool(out) and out[-1] in _NUMERAL_CHARS and nxt in _NUMERAL_CHARS


def normalize(text: str, latin_spaces: bool = False, pauses: bool = False) -> str:
    """NFKC and neologdn, then every whitespace, punctuation mark and
    non-spoken symbol removed by Unicode category rather than from a list
    (quotes, ♪, ※, ：, brackets). Latin casing is matched to the reference
    earlier (`notation.match_reference_case`).

    For the text cer_kana hands to OpenJTalk, two options keep what the reading
    depends on (the caller removes it from the reading afterwards):
    `latin_spaces` keeps one space between two Latin words and an apostrophe
    inside one (don't): read as one run, "dontgetinmyway" is spelled out.
    `pauses` keeps one 、 for a list separator or space between two numerals,
    where OpenJTalk's reading depends on it: 三、四週間 is サン、ヨン ("3 or 4
    weeks"), 三四週間 is サンジューヨン."""
    text = neologdn.normalize(unicodedata.normalize("NFKC", text))
    out, n = [], len(text)
    for i, ch in enumerate(text):
        if ch.isspace():
            nxt = text[i + 1:].lstrip()[:1]
            if latin_spaces and out and _ascii_letter(out[-1]) and nxt and _ascii_letter(nxt):
                out.append(" ")
            elif pauses and _between_numerals(out, nxt):
                out.append(PAUSE)
            continue
        if latin_spaces and ch == "'" and 0 < i < n - 1 and _ascii_letter(text[i - 1]) and _ascii_letter(text[i + 1]):
            out.append(ch)
            continue
        if ch in _DIGIT_JOINERS:
            if 0 < i < n - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
                out.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat in _INVISIBLE:
            continue
        if cat[0] == "P" or cat in ("So", "Sk"):
            if ch in _SPOKEN_SYMBOLS:
                out.append(ch)
            elif pauses and ch in _LIST_SEPARATORS and _between_numerals(out, text[i + 1:].lstrip()[:1]):
                out.append(PAUSE)
            continue
        out.append(ch)
    return "".join(out)
