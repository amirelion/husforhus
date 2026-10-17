"""pipeline/textfold.py: the search fold, pinned by the vectors web/fold.js is tested against too."""
import json
from pathlib import Path

import pytest

from pipeline.textfold import fold

VECTORS = json.loads((Path(__file__).parent.parent / "web/test/fixtures/fold.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("text", "folded"), VECTORS)
def test_fold_matches_the_shared_vectors(text, folded):
    assert fold(text) == folded


def test_fold_is_idempotent():
    for text, folded in VECTORS:
        assert fold(folded) == folded, text
