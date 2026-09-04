from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "tools")]

from retrieval_inspector.inspector import InspectorError, band_ranks  # noqa: E402


def test_rank_bands_are_deterministic_and_disjoint() -> None:
    assert band_ranks(1599) == {
        "most": [1], "top": list(range(2, 12)),
        "middle": list(range(795, 805)), "bottom": list(range(1590, 1600)),
    }
    nonlocal_bands = band_ranks(1513)
    flattened = [rank for ranks in nonlocal_bands.values() for rank in ranks]
    assert len(flattened) == len(set(flattened)) == 31
    assert nonlocal_bands["bottom"][-1] == 1513


def test_rank_bands_reject_too_small_population() -> None:
    with pytest.raises(InspectorError, match="31 candidates"):
        band_ranks(30)


def test_cli_import_has_no_side_effects() -> None:
    path = ROOT / "tools/render_retrieval_inspector.py"
    spec = importlib.util.spec_from_file_location("render_retrieval_inspector", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_source_is_read_only_and_does_not_run_inference() -> None:
    source = (ROOT / "tools/retrieval_inspector/inspector.py").read_text()
    for forbidden in ("evaluate_model(", "_embed(", "_embed_prepared(", "optimizer.step", "torch.load("):
        assert forbidden not in source
    assert 'embeddings = np.asarray(arrays["embeddings"], dtype=np.float32)[3200:]' in source
    assert "nonlocal_masks" in source


def test_static_interface_has_required_controls() -> None:
    html = (ROOT / "tools/retrieval_inspector/index.html").read_text()
    javascript = (ROOT / "tools/retrieval_inspector/app.js").read_text()
    for identifier in ("model", "query", "prevModel", "nextModel", "comparison"):
        assert f'id="{identifier}"' in html
    for phrase in ("Original spatial scene", "Most similar", "Top band", "Middle band", "Bottom band"):
        assert phrase in javascript
    assert "assets/scenes/${id}.js" in javascript
