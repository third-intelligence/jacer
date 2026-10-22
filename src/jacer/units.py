"""Units of measure: one published table, so a score never depends on which
dictionary build knows which unit.

  a unit    = an optional SI prefix + a base unit (km, mg, GHz, kWh, Mbps)
  a word    = the prefix word + the base word (キロメートル, ミリグラム)
  powers    = 平方 / 立方 + the word (m2 / ㎡ = 平方メートル)
  clipped   = the prefix word alone, as Japanese speech shortens units
              (5キロ for 5km or 5kg, 10センチ, 64ギガ); it matches each unit it
              can stand for, and the reference decides which one was meant

A unit id is the canonical symbol ("km", "m2"). A notation and a word match
when they name the same id with the same number; matching never looks at what
the unit measures.
"""

from __future__ import annotations

from functools import lru_cache

# base symbol -> (other symbols, words). Symbols are case-sensitive here;
# `unit_ids` retries an all-caps or all-lowercase notation (KM, KG) once.
BASE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "m": ((), ("メートル",)),
    "g": ((), ("グラム",)),
    "L": (("l", "ℓ"), ("リットル",)),
    "t": ((), ("トン",)),
    "s": (("sec",), ("秒",)),
    "min": ((), ("分",)),
    "h": (("hr",), ("時間",)),
    "Hz": ((), ("ヘルツ",)),
    "W": ((), ("ワット",)),
    "Wh": ((), ("ワット時", "ワットアワー")),
    "V": ((), ("ボルト",)),
    "A": ((), ("アンペア",)),
    "Ah": ((), ("アンペア時", "アンペアアワー")),
    "Pa": ((), ("パスカル",)),
    "N": ((), ("ニュートン",)),
    "J": ((), ("ジュール",)),
    "cal": ((), ("カロリー",)),
    "B": ((), ("バイト",)),
    "bit": ((), ("ビット",)),
    "bps": ((), ("ビーピーエス",)),
    "dB": ((), ("デシベル",)),
}

PREFIX: dict[str, str] = {
    "T": "テラ", "G": "ギガ", "M": "メガ", "k": "キロ", "h": "ヘクト",
    "d": "デシ", "c": "センチ", "m": "ミリ", "μ": "マイクロ", "µ": "マイクロ", "n": "ナノ",
    "K": "キロ",  # written for kilo in KB / Kbps only (see _PREFIXED); same unit as k
}
# Prefixes that combine with a base, per base: keeps nonsense ids (cs, Mt) out.
_PREFIXED = {
    "m": "kcmμµn", "g": "kmμµ", "L": "dmμµ", "t": "k", "s": "mμµn", "Hz": "kMGT",
    "W": "kMG", "Wh": "kMG", "V": "kmM", "A": "mμµ", "Ah": "m", "Pa": "hkM",
    "J": "kM", "cal": "k", "B": "kKMGT", "bit": "kMGT", "bps": "kKMGT", "dB": "",
}

# Symbols that are a unit by themselves.
SYMBOL: dict[str, tuple[str, ...]] = {
    "%": ("パーセント",),
    "°C": ("度",),  # NFKC turns ℃ into °C
    "°": ("度",),
}

# Clipped forms: the prefix word alone stands for these units.
CLIPPED: dict[str, tuple[str, ...]] = {
    "キロ": ("km", "kg", "kcal", "kW", "kB"),
    "センチ": ("cm",),
    "ミリ": ("mm", "mg", "mL"),
    "メガ": ("MB", "Mbps", "MHz", "MW"),
    "ギガ": ("GB", "Gbps", "GHz"),
    "テラ": ("TB",),
}

_POWER = {"2": "平方", "²": "平方", "3": "立方", "³": "立方"}
_POWERED = ("m", "km", "cm", "mm")


def _table() -> tuple[dict[str, str], dict[str, set[str]]]:
    """(notation -> unit id, word -> unit ids)."""
    notation, words = {}, {}

    def add(unit_id: str, symbols, unit_words):
        for s in symbols:
            notation.setdefault(s, unit_id)
        for w in unit_words:
            words.setdefault(w, set()).add(unit_id)

    for base, (alts, base_words) in BASE.items():
        add(base, (base, *alts), base_words)
        for p in _PREFIXED.get(base, ""):
            # K is written for kilo (KB, Kbps): same unit as k.
            add(("k" if p == "K" else p) + base, [p + s for s in (base, *alts)],
                [PREFIX[p] + w for w in base_words])
    for sym, sym_words in SYMBOL.items():
        add(sym, (sym,), sym_words)
    for u in _POWERED:
        for digit, power_word in _POWER.items():
            unit_words = [power_word + w for w, ids in words.items() if u in ids]
            add(u + ("2" if power_word == "平方" else "3"), (u + digit,), unit_words)
    add("cm3", ("cc",), ("シーシー",))
    for word, ids in CLIPPED.items():
        for i in ids:
            words.setdefault(word, set()).add(i)
    return notation, words


NOTATIONS, WORDS = _table()


@lru_cache(maxsize=None)
def unit_ids(notation: str) -> frozenset[str]:
    """The unit ids a written notation (km, ㎡ after NFKC, 5KG's KG) stands for."""
    for form in (notation, notation.lower(), notation.upper()):
        if form in NOTATIONS:
            return frozenset({NOTATIONS[form]})
    return frozenset()


def word_unit_ids(word: str) -> frozenset[str]:
    """The unit ids a written-out unit word stands for (キロ -> km, kg, ...)."""
    return frozenset(WORDS.get(word, ()))
