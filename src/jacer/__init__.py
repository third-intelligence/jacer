"""jacer: Japanese ASR scoring -- CER_strict, CER_flex and CER_kana.

    import jacer

    jacer.cer(references, hypotheses)                   # corpus cer_strict
    jacer.cer(references, hypotheses, jacer.METRICS)    # {"cer_strict": ..., "cer_flex": ..., "cer_kana": ...}
    jacer.error_counts(references, hypotheses)          # substitutions, deletions, insertions
    jacer.normalize_pair(ref, hyp, "cer_flex")          # the text a metric scores

`metric` defaults to "cer_strict", the primary score. Every function also
takes a list of metrics and then returns a dict keyed by metric.

`ErrorCounts` add up, so a corpus can be scored in shards (batches, workers)
and summed: the total's `.cer` equals `cer` over the whole set exactly.

`load_user_dict` adds readings for cer_kana (off by default; see
examples/user_dict.csv).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed

import jiwer

from jacer.kana import load_user_dict, normalize_pair_kana, unload_user_dict, user_dict
from jacer.ortho import FLEX, STRICT
from jacer.ortho import normalize_pair as _normalize_pair

METRICS_VERSION = "v1.2"
METRICS = ("cer_strict", "cer_flex", "cer_kana")

# The builds the metric definition was fixed with (see pyproject.toml): a
# different dictionary build tags, reads or normalizes differently.
SCORING_DEPENDENCIES = {"unidic-lite": "1.0.8", "fugashi": "1.5.2",
                        "pyopenjtalk-plus": "0.4.1.post8", "neologdn": "0.5.6",
                        "sudachipy": "0.6.11", "sudachidict-core": "20260428"}

_RULES = {"cer_strict": STRICT, "cer_flex": FLEX}


def _get(name: str) -> str | None:
    try:
        return _installed(name)
    except PackageNotFoundError:
        return None


__version__ = _get("jacer")


def scoring_environment() -> dict:
    """The metrics version, the installed builds of everything that affects a
    score and whether they are the pinned ones, and the user dictionary loaded
    for cer_kana (None by default). Publish it next to the numbers: the same
    metrics version under a different dictionary is not the same metric."""
    deps = {name: _get(name) for name in SCORING_DEPENDENCIES}
    return {"metrics_version": METRICS_VERSION, "jacer": __version__, "dependencies": deps,
            "pinned": deps == SCORING_DEPENDENCIES, "user_dict": user_dict()}


def _for_each(metric: str | Sequence[str], score):
    """score(metric), or {m: score(m)} for a list of metrics."""
    if isinstance(metric, str):
        return score(metric)
    return {m: score(m) for m in metric}


def _normalize_one(reference: str, hypothesis: str, metric: str) -> tuple[str, str]:
    if metric == "cer_kana":
        return normalize_pair_kana(reference, hypothesis)
    if metric not in _RULES:
        raise KeyError(f"unknown metric {metric!r}; one of {METRICS}")
    return _normalize_pair(reference, hypothesis, _RULES[metric])


def normalize_pair(reference: str, hypothesis: str, metric: str | Sequence[str] = "cer_strict"):
    """(reference, hypothesis) exactly as `metric` scores them. The reference is
    never rewritten toward the hypothesis, only normalized; cer_kana returns
    katakana readings."""
    return _for_each(metric, lambda m: _normalize_one(reference, hypothesis, m))


@dataclass(frozen=True)
class ErrorCounts:
    """Character edits between normalized texts, and the reference length."""
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0
    reference_chars: int = 0

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def cer(self) -> float | None:
        """errors / reference_chars, or None when there is no reference text."""
        return self.errors / self.reference_chars if self.reference_chars else None

    def __add__(self, other: "ErrorCounts") -> "ErrorCounts":
        return ErrorCounts(self.substitutions + other.substitutions, self.deletions + other.deletions,
                           self.insertions + other.insertions, self.reference_chars + other.reference_chars)


def _pair_counts(reference: str, hypothesis: str, metric: str) -> ErrorCounts:
    ref, hyp = _normalize_one(reference, hypothesis, metric)
    if not ref.strip():
        return ErrorCounts()  # CER is undefined without reference text: the pair is skipped
    out = jiwer.process_characters(ref, hyp)
    return ErrorCounts(out.substitutions, out.deletions, out.insertions, len(ref))


def error_counts(reference: str | list[str], hypothesis: str | list[str],
                 metric: str | Sequence[str] = "cer_strict"):
    """Substitutions, deletions and insertions under `metric`, for one pair
    (two strings) or summed over a corpus (two lists). A pair whose reference
    normalizes to empty counts nothing."""
    if isinstance(reference, str) != isinstance(hypothesis, str):
        raise TypeError("pass two strings or two lists")
    if isinstance(reference, str):
        return _for_each(metric, lambda m: _pair_counts(reference, hypothesis, m))
    if len(reference) != len(hypothesis):
        raise ValueError("references and hypotheses must be the same length")
    return _for_each(metric, lambda m: sum((_pair_counts(r, h, m) for r, h in zip(reference, hypothesis)),
                                           ErrorCounts()))


def cer(references: list[str], hypotheses: list[str], metric: str | Sequence[str] = "cer_strict"):
    """Corpus CER: total edits over total reference characters. Pairs whose
    reference normalizes to empty are skipped; None if none remains."""
    counts = error_counts(references, hypotheses, metric)
    return counts.cer if isinstance(counts, ErrorCounts) else {m: c.cer for m, c in counts.items()}


__all__ = ["METRICS_VERSION", "METRICS", "SCORING_DEPENDENCIES", "scoring_environment",
           "cer", "error_counts", "ErrorCounts", "normalize_pair", "load_user_dict", "unload_user_dict"]
