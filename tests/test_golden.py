"""The exact text every metric scores for each edge case in golden/ja_pairs.tsv
is pinned in golden/expected_v1.2.json. Any byte of difference is a change to
the metric definition."""
import json
from pathlib import Path

import pytest

from jacer import METRICS, METRICS_VERSION, normalize_pair

GOLDEN = Path(__file__).parent / "golden"


def load_pairs() -> list[tuple[str, str]]:
    out = []
    for line in (GOLDEN / "ja_pairs.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            r, h = line.split("\t")
            out.append((json.loads(f'"{r}"'), json.loads(f'"{h}"')))
    return out


EXPECTED = json.loads((GOLDEN / f"expected_{METRICS_VERSION}.json").read_text(encoding="utf-8"))
PAIRS = load_pairs()


@pytest.mark.parametrize("key", METRICS)
def test_golden(key):
    assert key in METRICS
    got = [list(normalize_pair(r, h, key)) for r, h in PAIRS]
    diffs = [(i, e, g) for i, (e, g) in enumerate(zip(EXPECTED[key], got)) if e != g]
    assert len(got) == len(EXPECTED[key]) and not diffs, f"{key}: {len(diffs)} pair(s) changed, first: {diffs[:1]}"
