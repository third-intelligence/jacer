"""The scoring dependencies jacer reports must be the ones pyproject.toml pins."""
import re
from pathlib import Path

from jacer import SCORING_DEPENDENCIES


def test_reported_pins_match_pyproject():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    pinned = dict(re.findall(r'^\s*"([A-Za-z0-9_.-]+)==([^"]+)",', pyproject, flags=re.M))
    assert pinned == SCORING_DEPENDENCIES
