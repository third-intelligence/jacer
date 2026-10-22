"""Lemma alignment that resolves Japanese orthographic variants before CER.

Both texts are tagged with UniDic (via fugashi), hypothesis tokens are aligned
to reference tokens, and a hypothesis token is rewritten to the reference's
spelling when the two are the SAME WORD written differently. Only the
hypothesis is ever moved toward the reference; what counts as "the same word
written differently" is what separates the metrics:

  cer_strict  notation conventions within one script: both spellings carry
              the identical kanji and only the kana around them differ
              (申し込む/申込む, 取り扱い/取扱い), the counter ヶ/か (3ヶ月/3か月),
              々 (時々/時時), and katakana transliteration of one loanword
              (コンピューター/コンピュータ). A kanji<->kana script choice
              (お願い/おねがい) or a different kanji (聞く/聴く) is an error.
  cer_flex    any script choice for the same word: everything strict forgives,
              plus kanji<->kana (お願い/おねがい, 私/わたし, 綺麗/きれい), a different
              kanji (聞く/聴く), and hiragana<->katakana (りんご/リンゴ). Two kana
              spellings of DIFFERENT pronunciations (にほん/にっぽん) are an
              error: each commits to what was said.

Numbers follow the reference's format: a hypothesis number of equal value
takes the reference's spelling (百八十五/185, 三万五千/35000/3万5000/35,000), and a
wrong one is written in the reference's style so it earns partial credit
character by character. Different words that merely sound alike (機関/期間) are
never paired here; `cer_kana` is the metric that folds those.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

import fugashi

from jacer.notation import match_reference_notation
from jacer.numerals import DIGIT_KANJI, KANJI_DIGIT, format_like, numeral_value
from jacer.text import normalize, preclean

tagger = fugashi.Tagger()

# UniDic POS labels this module keys on. Punctuation morphemes skip
# alignment; numerals are tagged 名詞 with pos2 数詞.
_PUNCT_POS1 = "補助記号"
_NUMERAL_POS2 = "数詞"
_NUMERAL_POS1 = "数詞"  # marker pos1 given to a merged numeral run
_NUMERAL_COMPOUND_POS2 = "数詞複合"  # marker pos2 given to a joined number + counter

# A UniDic lemma is a headword optionally followed by "-" and a disambiguator:
# a POS label where two words share a written headword (私-代名詞 is わたくし,
# 私 is わたし) or an English gloss for loanwords (コーヒー-coffee).
_LEMMA_SEP = "-"


class Token(NamedTuple):
    lemma: str
    surface: str
    pos1: str
    pos2: str


# --------------------------------------------------------------------------
# Script helpers
# --------------------------------------------------------------------------

def _is_kanji(ch: str) -> bool:
    name = unicodedata.name(ch, "")
    return name.startswith(("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH")) or name == "IDEOGRAPHIC ITERATION MARK"


def _has_kanji(surface: str) -> bool:
    return any(_is_kanji(ch) for ch in surface)


def _has_kana(surface: str) -> bool:
    return any("ぁ" <= ch <= "ヺ" for ch in surface)


def _kanji_of(surface: str) -> str:
    """The kanji of a spelling, 々 written out as the kanji it repeats."""
    out = ""
    for ch in surface:
        if ch == "々" and out:
            out += out[-1]
        elif _is_kanji(ch):
            out += ch
    return out


def _to_katakana(surface: str) -> str:
    # Hiragana and katakana sit at a fixed 0x60 offset in Unicode.
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch for ch in surface)


# The counter ヶ / ヵ is a whole word although it is a small kana.
_COUNTER_INITIALS = frozenset("ヶヵ")


def _is_word_initial(ch: str) -> bool:
    """False for characters no Japanese word begins with: small kana (っ, ゃ)
    and the long-vowel mark. A token starting with one is a fragment left by
    segmenting the two texts differently (げ|っ歯 vs げっ|歯)."""
    if ch in _COUNTER_INITIALS:
        return True
    name = unicodedata.name(ch, "")
    return not ("SMALL" in name and ("HIRAGANA" in name or "KATAKANA" in name)) \
        and name != "KATAKANA-HIRAGANA PROLONGED SOUND MARK"


def _whole_words(ref: Token, hyp: Token) -> bool:
    """Both tokens are whole words, so copying the reference spelling over the
    hypothesis cannot duplicate or drop a kana the neighbouring token holds."""
    return all(t.surface and _is_word_initial(t.surface[0]) for t in (ref, hyp))


def _headword(lemma: str) -> str:
    return lemma.split(_LEMMA_SEP, 1)[0]


def _is_katakana_word(surface: str) -> bool:
    return bool(surface) and all("ァ" <= ch <= "ヺ" or ch == "ー" for ch in surface)


# Katakana transliteration conventions folded away when comparing two
# spellings of one loanword: the long-vowel mark, small vowels, and ヴ.
_TRANSLIT_FOLD = str.maketrans({"ァ": "ア", "ィ": "イ", "ゥ": "ウ", "ェ": "エ", "ォ": "オ", "ヮ": "ワ", "ー": None})
_VU = {"ヴァ": "バ", "ヴィ": "ビ", "ヴェ": "ベ", "ヴォ": "ボ", "ヴ": "ブ"}


def _transliteration_key(surface: str) -> str:
    for vu, b in _VU.items():
        surface = surface.replace(vu, b)
    return surface.translate(_TRANSLIT_FOLD)


# --------------------------------------------------------------------------
# Pairing and forgiveness
# --------------------------------------------------------------------------

def _same_word(ref: Token, hyp: Token) -> bool:
    """One dictionary word, possibly spelled differently.

    Identical lemmas always pair. Lemmas sharing a headword but carrying
    different disambiguators pair only when a side is written in kanji: bare
    私 is ambiguous between わたし and わたくし, so the tagger's guess of one
    must not turn the other into a different word. Two kana spellings are not
    ambiguous -- わたし/わたくし each commit to a pronunciation -- so they keep
    their distinct lemmas and stay a substitution.
    """
    if ref.lemma == hyp.lemma:
        return True
    if ref.pos1 == hyp.pos1 == _NUMERAL_POS1:
        return True  # any two numbers align; the wrong one is rewritten in the reference's style
    return (_headword(ref.lemma) == _headword(hyp.lemma)
            and (_has_kanji(ref.surface) or _has_kanji(hyp.surface)))


def _loanword_variant(ref: Token, hyp: Token) -> bool:
    """One loanword (a lemma glossed with its source word: コンピューター-computer)
    spelled in katakana two ways that differ only in transliteration convention
    (コンピュータ / コンピューター, ヴァイオリン / バイオリン). The same lemma alone is
    not enough: UniDic gives トップス the lemma トップ-top."""
    _, sep, gloss = ref.lemma.partition(_LEMMA_SEP)
    return (ref.lemma == hyp.lemma and bool(sep) and gloss.isascii()
            and _is_katakana_word(ref.surface) and _is_katakana_word(hyp.surface)
            and _transliteration_key(ref.surface) == _transliteration_key(hyp.surface))


def _okurigana_variant(ref: Token, hyp: Token) -> bool:
    """Same kanji on both sides (々 written out); only the kana around them
    differ. Or one loanword's transliteration variants."""
    kanji = _kanji_of(ref.surface)
    return ((bool(kanji) and kanji == _kanji_of(hyp.surface) and _whole_words(ref, hyp))
            or _loanword_variant(ref, hyp))


def _script_variant(ref: Token, hyp: Token) -> bool:
    """Any spelling of the same word that does not commit to a different
    pronunciation: a kanji side (whose reading the other side supplies), or
    two kana spellings of the same sound (hiragana vs katakana)."""
    if _loanword_variant(ref, hyp):
        return True
    if not _whole_words(ref, hyp):
        return False
    if _has_kanji(ref.surface) or _has_kanji(hyp.surface):
        return True
    return _to_katakana(ref.surface) == _to_katakana(hyp.surface)


@dataclass(frozen=True)
class Rules:
    """What distinguishes the pair one metric scores.

    forgive             which spellings of one word are not an error
    rewrite_wrong_numbers
                        a number of a different value is written in the
                        reference's style (partial credit). False for the
                        pair cer_kana reads, where restyling a wrong number
                        changes how it is read.
    for_reading         the text is for G2P: Latin words keep their spaces and
                        numerals their list separators (`text.normalize`)
    """
    forgive: Callable[[Token, Token], bool]
    rewrite_wrong_numbers: bool = True
    for_reading: bool = False


STRICT = Rules(_okurigana_variant)
FLEX = Rules(_script_variant)
# A wrong number keeps its own spelling: restyled as the reference writes
# numbers, it would be read differently, not more closely.
KANA = Rules(_script_variant, rewrite_wrong_numbers=False, for_reading=True)


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------

_GROUP_COMMA_RE = re.compile(r"(?<=\d)、(?=\d{3}(?!\d))")
_CODE_HYPHENS = frozenset("-－‐–—")


def _is_digits(surface: str) -> bool:
    s = unicodedata.normalize("NFKC", surface)
    return s.isascii() and s.isdigit()


def _is_digit_group(surface: str) -> bool:
    return len(unicodedata.normalize("NFKC", surface)) == 3 and _is_digits(surface)


def _is_digit_string(surface: str) -> bool:
    """A run of digits with a leading zero (0110, 〇一〇): a code or a bit
    string read digit by digit, which has no numeric value to compare."""
    s = unicodedata.normalize("NFKC", surface)
    return len(s) > 1 and s[0] in "0〇零" and s[1] not in ".点"


def _digits_of(surface: str) -> str | None:
    """The digit sequence of a digit-by-digit string (〇一〇 / 010 -> "010")."""
    s = "".join(c for c in unicodedata.normalize("NFKC", surface) if c != "," and c not in _CODE_HYPHENS)
    out = "".join(c if c.isascii() and c.isdigit() else str(KANJI_DIGIT[c]) if c in KANJI_DIGIT else "" for c in s)
    return out if len(out) == len(s) else None


def _restyle_digits(hyp: str, ref: str) -> str | None:
    """`hyp`'s digits written one by one in `ref`'s digit glyphs (0101 against
    〇一〇一 -> 〇一〇一), so a code compares digit by digit; None if either is
    not a plain digit string."""
    h, r = _digits_of(hyp), _digits_of(ref)
    if h is None or r is None:
        return None
    if any(c.isascii() and c.isdigit() for c in unicodedata.normalize("NFKC", ref)):
        return h
    zero = "零" if "零" in ref else "〇"
    return "".join(zero if d == "0" else DIGIT_KANJI[int(d)] for d in h)


def _numeral_token(run: list[Token]) -> Token:
    """One token for a run of numeral morphemes (separators included). Its
    lemma is "#<value>", or its spelling when it has no value."""
    surface = "".join(t.surface for t in run)
    # 、 as a group separator (１、０００), not in a list (三、四)
    digits = _GROUP_COMMA_RE.sub("", unicodedata.normalize("NFKC", surface).replace(",", ""))
    value = numeral_value(digits)
    if _is_digit_string(surface):
        value = None  # 0110 is a code, not the number 110
    elif value is None and _has_kana(surface):
        # A numeral spelled in kana takes its value from UniDic's lemma
        # (ひと -> 一). Only then: 三、四 is a list, not the number 34.
        value = numeral_value("".join(t.lemma for t in run if t.pos2 == _NUMERAL_POS2))
    return Token(surface if value is None else f"#{value}", surface, _NUMERAL_POS1, _NUMERAL_POS2)


def _joins_numeral(sep: Token, before: Token, after: Token) -> bool:
    """`sep` separates digit groups of one number or code: "," (UniDic tags it
    記号, not punctuation), 、 before exactly three digits (１、０００), or a
    hyphen between digit groups (090-1234-5678)."""
    return (unicodedata.normalize("NFKC", sep.surface) == ","
            or (sep.surface == "、" and _is_digit_group(after.surface))
            or (sep.surface in _CODE_HYPHENS and _is_digits(before.surface) and _is_digits(after.surface)))


def _merge_numerals(tokens: list[Token]) -> list[Token]:
    """Merge each run of numeral morphemes into one token, so a multi-morpheme
    kanji number meets the other side's digit string as one unit."""
    out, run = [], []
    for i, tok in enumerate(tokens):
        if tok.pos2 == _NUMERAL_POS2:
            run.append(tok)
        elif (run and i + 1 < len(tokens) and tokens[i + 1].pos2 == _NUMERAL_POS2
              and _joins_numeral(tok, run[-1], tokens[i + 1])):
            run.append(tok)
        else:
            if run:
                out.append(_numeral_token(run))
                run = []
            out.append(tok)
    if run:
        out.append(_numeral_token(run))
    return out


# A joined word is a small number and a counter of one or two characters
# (一人, 二人, 一番); beyond that UniDic has no single-word entries to find.
_COMPOUND_MAX_VALUE = 99
_COMPOUND_MAX_COUNTER = 2


@lru_cache(maxsize=4096)
def _single_word_lemma(text: str) -> str | None:
    words = list(tagger(text))
    return (words[0].feature.lemma or None) if len(words) == 1 else None


def _join_numeral_compounds(tokens: list[Token], other: set[str]) -> list[Token]:
    """A number and the token after it become one word when their kanji form
    is a single UniDic word that `other` (the other text's lemmas) also has.
    UniDic keeps 一人 / 二人 / 一番 whole but splits 1人 into 1 + 人; joined, 1人
    carries the lemma 一人 and meets 一人 or ひとり as one word."""
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if (tok.pos1 == _NUMERAL_POS1 and tok.lemma.startswith("#") and i + 1 < len(tokens)
                and len(tokens[i + 1].surface) <= _COMPOUND_MAX_COUNTER and tokens[i + 1].pos1 != _PUNCT_POS1):
            value = int(tok.lemma[1:])
            lemma = (_single_word_lemma(format_like(value, "一") + tokens[i + 1].surface)
                     if value <= _COMPOUND_MAX_VALUE else None)
            if lemma and lemma in other:
                out.append(Token(lemma, tok.surface + tokens[i + 1].surface, tok.pos1, _NUMERAL_COMPOUND_POS2))
                i += 2
                continue
        out.append(tok)
        i += 1
    return out


def _rewrite_numeral(ref: Token, hyp: Token) -> str:
    """A paired number: the reference's spelling if the values agree, else the
    hypothesis's value in the reference's style (so 1888 against 千八百八十九
    is one kanji off, not four digits against six kanji)."""
    if ref.lemma == hyp.lemma:
        return ref.surface
    if ref.lemma.startswith("#") and hyp.lemma.startswith("#"):
        return format_like(int(hyp.lemma[1:]), ref.surface)
    return hyp.surface


def _numeral_rewrite(ref: Token, hyp: Token, rules: Rules) -> str | None:
    """The hypothesis spelling for a paired number (or number + counter), or
    None to leave it as written."""
    same = ref.lemma == hyp.lemma
    if _is_digit_string(ref.surface):
        # The reference is a code read digit by digit (0110): compared in its
        # glyphs, never as a value.
        restyled = _restyle_digits(hyp.surface, ref.surface)
        if restyled is not None and (rules.rewrite_wrong_numbers or _digits_of(hyp.surface) == _digits_of(ref.surface)):
            return restyled
        return None
    if _is_digit_string(hyp.surface) and ref.lemma.startswith("#"):
        # Only the hypothesis looks like a code (000 against 千): a number,
        # compared by value like any other.
        value = numeral_value(hyp.surface)
        if value is not None and (rules.rewrite_wrong_numbers or f"#{value}" == ref.lemma):
            return ref.surface if f"#{value}" == ref.lemma else format_like(value, ref.surface)
        return None
    if same and _has_kana(ref.surface + hyp.surface):
        # ひと / 一, ひとり / 1人: a kana spelling is a script choice.
        return ref.surface if rules.forgive(ref, hyp) else None
    if _NUMERAL_COMPOUND_POS2 in (ref.pos2, hyp.pos2):
        return ref.surface if same else None  # 一人 / 1人: a numeral format
    if rules.rewrite_wrong_numbers or same:
        return _rewrite_numeral(ref, hyp)
    return None


# --------------------------------------------------------------------------
# Alignment
# --------------------------------------------------------------------------

def _tokens(text: str) -> list[Token]:
    """All tokens that make up the text; punctuation morphemes among them
    skip alignment but stay in the text."""
    return _merge_numerals([Token(w.feature.lemma or w.surface, w.surface, w.feature.pos1, w.feature.pos2)
                            for w in tagger(text)])


# How an alignment cell was reached.
_DIAGONAL, _DELETION, _INSERTION = 0, 1, 2


class _Cell:
    """Edit-distance cell. `cost` counts edits; `paired` counts diagonal steps
    whose tokens are the same word. `score` ranks by cost first and breaks ties
    toward more pairs, so among minimum-cost alignments the one lining up the
    same words wins (`radix` exceeds any possible pair count)."""
    radix = 100000

    def __init__(self, cost: float = 0.0, paired: int = 0, step: int = _DIAGONAL, same: bool = False):
        self.cost, self.paired, self.step, self.same = cost, paired, step, same

    def diagonal(self, same: bool) -> "_Cell":
        return _Cell(self.cost + (not same), self.paired + same, _DIAGONAL, same)

    def deletion(self) -> "_Cell":
        return _Cell(self.cost + 1, self.paired, _DELETION)

    def insertion(self) -> "_Cell":
        return _Cell(self.cost + 1, self.paired, _INSERTION)

    def score(self) -> float:
        return self.cost * self.radix - self.paired


def _align(ref: list[Token], hyp: list[Token]) -> list[tuple[int, int]]:
    """(ref_idx, hyp_idx) of every diagonal step whose tokens are the same word."""
    n_ref, n_hyp = len(ref), len(hyp)
    cell = [[_Cell() for _ in range(n_hyp + 1)] for _ in range(n_ref + 1)]
    for j in range(n_hyp + 1):
        cell[0][j].cost, cell[0][j].step = j, _INSERTION
    for i in range(n_ref + 1):
        cell[i][0].cost, cell[i][0].step = i, _DELETION
    for r in range(1, n_ref + 1):
        for h in range(1, n_hyp + 1):
            cell[r][h] = min(
                (cell[r - 1][h - 1].diagonal(_same_word(ref[r - 1], hyp[h - 1])),
                 cell[r - 1][h].deletion(),
                 cell[r][h - 1].insertion()),
                key=_Cell.score)
    pairs = []
    r, h = n_ref, n_hyp
    while r > 0 or h > 0:
        c = cell[r][h]
        if c.step == _DIAGONAL:
            if c.same:
                pairs.append((r - 1, h - 1))
            r, h = r - 1, h - 1
        elif c.step == _DELETION:
            r -= 1
        else:
            h -= 1
    return pairs[::-1]


def align_orthographic_variants(reference: str, hypothesis: str, rules: Rules) -> tuple[str, str]:
    """Rewrite hypothesis tokens that are a forgiven spelling of the reference
    token they align with; return (reference, hypothesis) as text, before
    character normalization. The reference is returned as written."""
    ref_all, hyp_all = _tokens(reference), _tokens(hypothesis)
    ref_lemmas, hyp_lemmas = {t.lemma for t in ref_all}, {t.lemma for t in hyp_all}
    ref_all = _join_numeral_compounds(ref_all, hyp_lemmas)
    hyp_all = _join_numeral_compounds(hyp_all, ref_lemmas)
    ref_idx = [i for i, t in enumerate(ref_all) if t.pos1 != _PUNCT_POS1]
    hyp_idx = [i for i, t in enumerate(hyp_all) if t.pos1 != _PUNCT_POS1]
    ref = [ref_all[i] for i in ref_idx]
    hyp = [hyp_all[i] for i in hyp_idx]
    surfaces = [t.surface for t in hyp_all]
    for r, h in _align(ref, hyp):
        if ref[r].pos1 == _NUMERAL_POS1 or hyp[h].pos2 == _NUMERAL_COMPOUND_POS2:
            rewritten = _numeral_rewrite(ref[r], hyp[h], rules)
        else:
            rewritten = ref[r].surface if rules.forgive(ref[r], hyp[h]) else None
        if rewritten is not None:
            surfaces[hyp_idx[h]] = rewritten
    return "".join(t.surface for t in ref_all), "".join(surfaces)


# --------------------------------------------------------------------------
# The scored pair
# --------------------------------------------------------------------------

def normalize_pair(reference: str, hypothesis: str, rules: Rules) -> tuple[str, str]:
    """The (reference, hypothesis) text one metric scores: brackets and
    invisible characters out, notation matched, the alignment that rewrites
    forgiven spellings, then character normalization."""
    reference, hypothesis = preclean(reference, hypothesis)
    hypothesis = match_reference_notation(reference, hypothesis)
    ref, hyp = align_orthographic_variants(reference, hypothesis, rules)
    opts = {"latin_spaces": rules.for_reading, "pauses": rules.for_reading}
    return normalize(ref, **opts), normalize(hyp, **opts)
