from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import canonical_yaml_sha256, load_strict_yaml


def test_formatting_comments_and_mapping_order_do_not_change_identity(tmp_path):
    left = tmp_path / "left.yml"
    right = tmp_path / "right.yml"
    left.write_text("a: 1\nb: [x, y]\n", encoding="utf-8")
    right.write_text("# provenance comment\nb:\n  - x\n  - y\na: 1\n\n", encoding="utf-8")
    assert canonical_yaml_sha256(left) == canonical_yaml_sha256(right)


def test_semantic_value_and_sequence_changes_change_identity(tmp_path):
    base = tmp_path / "base.yml"
    value = tmp_path / "value.yml"
    sequence = tmp_path / "sequence.yml"
    base.write_text("a: 1\nb: [x, y]\n", encoding="utf-8")
    value.write_text("a: 2\nb: [x, y]\n", encoding="utf-8")
    sequence.write_text("a: 1\nb: [y, x]\n", encoding="utf-8")
    assert canonical_yaml_sha256(base) != canonical_yaml_sha256(value)
    assert canonical_yaml_sha256(base) != canonical_yaml_sha256(sequence)


@pytest.mark.parametrize("payload", ["a: 1\na: 2\n", "a: .nan\n", "a: !!python/object:builtins.str {}\n"])
def test_unsafe_or_ambiguous_yaml_is_rejected(tmp_path, payload):
    path = tmp_path / "bad.yml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises((ValueError, Exception)):
        load_strict_yaml(path)


def test_p6_committed_canonical_checksum():
    assert canonical_yaml_sha256(ROOT / "config/p6_model_dataloader.yml") == (
        "499cda4904633b052a5b55e50212d7f8dc423fe7ece9bdb8e823e1d44c4d21f8"
    )
