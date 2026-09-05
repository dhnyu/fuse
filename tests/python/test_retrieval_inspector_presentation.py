import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "tools")]
from retrieval_inspector.inspector import InspectorError
from retrieval_inspector.presentation import accepted_evidence, digest, immutable, publish_update, require_hash


def test_immutable_presentation_collision_and_hash_guard(tmp_path):
    path = tmp_path / "receipt.json"
    immutable(path, b"accepted")
    immutable(path, b"accepted")
    with pytest.raises(InspectorError, match="collision"):
        immutable(path, b"changed")
    require_hash(path, digest(path))
    with pytest.raises(InspectorError, match="checksum"):
        require_hash(path, "0" * 64)


def test_publication_requires_complete_browser_gate(tmp_path):
    (tmp_path / "presentation.json").write_text(json.dumps({"presentation_id":"fixture"}))
    with pytest.raises(InspectorError, match="browser validation"):
        publish_update(tmp_path, tmp_path, {"status":"PASS","desktop_states":159})


def test_presentation_does_not_offer_scientific_execution():
    source = (ROOT / "tools/retrieval_inspector/presentation.py").read_text()
    for forbidden in ("rank_gallery(", "build_rank_manifest(", "np.load(", "torch.load(", "_scene_assets(", "tar_make("):
        assert forbidden not in source


def test_accepted_map_and_summary_rendering_functions_unchanged():
    pointer = json.loads((ROOT / "tools/retrieval_inspector/supplemental_output.json").read_text())
    old = Path(pointer["acceptance_path"]).parent.parent / "inspector/app.js"
    if not old.exists():
        pytest.skip("Accepted local presentation unavailable")
    current = (ROOT / "tools/retrieval_inspector/app.js").read_text().splitlines()
    accepted = old.read_text().splitlines()
    for name in ("drawVector", "drawRaster", "pathSets", "viridis", "summary"):
        prefix = "function " + name + "("
        assert next(x for x in current if x.startswith(prefix)) == next(x for x in accepted if x.startswith(prefix))


def test_accepted_canonical_and_expanded_readback():
    pointer = json.loads((ROOT / "tools/retrieval_inspector/supplemental_output.json").read_text())
    output = Path(pointer["acceptance_path"]).parent.parent / "inspector"
    if not output.exists():
        pytest.skip("Accepted local evidence unavailable")
    evidence = accepted_evidence(ROOT, output)
    assert evidence["validation"] == {"canonical_states":160,"expanded_states":160,
        "band_items_checked":9920,"asset_count":3622,"canonical_assets_unchanged":1342,"status":"PASS"}
    for model in evidence["diagnostics"].values():
        assert len(model) == 10
        for query in model.values():
            assert set(query) == {"standard","nonlocal"}
            assert query["nonlocal"]["diagnostic"]["new_best_distance_m"] >= 2000
