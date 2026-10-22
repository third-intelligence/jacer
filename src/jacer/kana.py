"""cer_kana: the pair cer_flex scores, read as katakana by OpenJTalk.

Everything cer_flex forgives is forgiven here too (20歳 / 二十歳 read alike once
the number follows the reference); kana adds the homophones flex cannot pair
(機関 / 期間), at the cost of inheriting OpenJTalk's reading mistakes.
"""

import contextlib
import ctypes
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

import pyopenjtalk

from jacer.notation import times_as_words
from jacer.ortho import KANA, normalize_pair, tagger
from jacer.text import PAUSE

# --------------------------------------------------------------------------
# User dictionary (optional)
# --------------------------------------------------------------------------
# Readings OpenJTalk lacks, so a name is read as a Japanese speaker says it
# (Siri is シリ, not エスアイアールアイ). None is loaded by default: the metric
# definition is OpenJTalk's own dictionary. See examples/user_dict.csv.

_user_dict: dict | None = None


@contextlib.contextmanager
def _quiet_native_stdout():
    """mecab_dict_index prints a progress bar straight to fd 1, bypassing
    sys.stdout: redirect the fd itself, flushing native stdio before
    restoring it."""
    if sys.platform == "win32":
        yield
        return
    libc = ctypes.CDLL(None)
    saved_fd = os.dup(1)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 1)
    try:
        yield
    finally:
        libc.fflush(None)
        os.dup2(saved_fd, 1)
        os.close(devnull_fd)
        os.close(saved_fd)


def load_user_dict(csv_path: str | os.PathLike) -> None:
    """Add the readings in a MeCab/OpenJTalk user-dictionary CSV to cer_kana,
    replacing any loaded before. Rows are
        surface,left-id,right-id,cost,pos,pos1,pos2,pos3,ctype,cform,orig,read,pron,acc/mora,chain_rule
    with left-id/right-id blank (inferred from the POS fields). OpenJTalk
    full-width-normalizes ASCII before tagging, so a Latin surface is written
    full-width (Ｓｉｒｉ); a half-width entry silently never matches.

    This changes pyopenjtalk's global instance for the whole process, and
    cer_kana scores with it are no longer the standard definition:
    `scoring_environment()` reports the dictionary loaded."""
    global _user_dict
    path = Path(csv_path).resolve()
    # The compiled dictionary stays in its temp dir for the process's
    # lifetime: OpenJTalk keeps it memory-mapped.
    dic_path = str(Path(tempfile.mkdtemp(prefix="jacer_user_dict_")) / "user_dict.dic")
    with _quiet_native_stdout():
        pyopenjtalk.mecab_dict_index(str(path), dic_path)
    pyopenjtalk.update_global_jtalk_with_user_dict(dic_path)
    _user_dict = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def unload_user_dict() -> None:
    """Back to OpenJTalk's own dictionary."""
    global _user_dict
    pyopenjtalk.unset_user_dict()
    _user_dict = None


def user_dict() -> dict | None:
    """The loaded user dictionary ({"path", "sha256"}), or None."""
    return _user_dict


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

_KANA_CHUNK = 1000


def _g2p(text: str) -> str:
    try:
        return pyopenjtalk.g2p(text, kana=True)
    except RuntimeError as exc:
        # OpenJTalk's MeCab buffer caps input at ~8 KB of UTF-8 (~2,700
        # chars), which only a runaway hypothesis (a repetition loop) reaches.
        # Fall back to fixed chunks only on that error.
        if "too long" not in str(exc):
            raise
        return "".join(pyopenjtalk.g2p(text[i:i + _KANA_CHUNK], kana=True)
                       for i in range(0, len(text), _KANA_CHUNK))


_UNREAD_RE = re.compile(r"[぀-ゟ㐀-䶿一-鿿豈-﫿]")


def _g2p_complete(text: str) -> str:
    """`_g2p` that never returns kanji or hiragana. OpenJTalk returns some runs
    unread (二世絶来展住後前死); such a text is split in half at a word boundary
    and each half read again, keeping as much context as possible (家 is ケ in
    横田家, イエ alone), and a single word OpenJTalk still cannot read takes
    UniDic's reading."""
    out = _g2p(text)
    if not _UNREAD_RE.search(out):
        return out
    words = list(tagger(text))
    if len(words) <= 1:
        return (getattr(words[0].feature, "pron", None) or out) if words else out
    mid = len(words) // 2
    return (_g2p_complete("".join(w.surface for w in words[:mid]))
            + _g2p_complete("".join(w.surface for w in words[mid:])))


def reading(text: str) -> str:
    """Katakana reading of normalized text; the pauses the text kept for
    OpenJTalk are not part of it."""
    return _g2p_complete(text).replace(PAUSE, "")


def normalize_pair_kana(reference: str, hypothesis: str) -> tuple[str, str]:
    """(reference, hypothesis) as katakana readings of the flex-aligned pair,
    clock times read as words (6:00 -> 6時)."""
    ref, hyp = normalize_pair(reference, hypothesis, KANA)
    return reading(times_as_words(ref)), reading(times_as_words(hyp))
