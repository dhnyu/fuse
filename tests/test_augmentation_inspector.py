from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from augmentation_inspector.inspector import (  # noqa: E402
    EXPECTED,
    AcceptedArtifacts,
    InspectorError,
    _candidate_slice_checksum,
    _coordinates,
    _normalize,
    _template,
    canonical_json,
    validate_html,
)


def minimal_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "tool": "P4 augmentation inspector",
        "scientific_status": "supplementary human visual QC; not scientific acceptance",
        "artifact_ids": {
            "p3_cache_id": EXPECTED["p3_cache"],
            "p3_acceptance_id": EXPECTED["p3_acceptance"],
            "p4_supplement_version": EXPECTED["supplement"],
            "p4_master_bank_id": EXPECTED["p4_bank"],
            "p4_logical_index_id": EXPECTED["p4_index"],
        },
        "cases": [{"scene_id": "scn_fixture", "master_view_id": 0}],
    }


def write_html(path: Path, payload: dict | None = None) -> None:
    encoded = canonical_json(payload or minimal_payload()).decode().replace("<", "\\u003c")
    path.write_text(_template(encoded), encoding="utf-8")


def test_template_is_standalone_and_has_required_controls(tmp_path: Path) -> None:
    output = tmp_path / "inspector.html"
    write_html(output)
    result = validate_html(output, expected_cases=1)
    text = output.read_text()
    assert result["status"] == "PASS"
    assert result["case_count"] == 1
    assert "https://" not in text and "http://" not in text
    assert "/mnt/hdd002/" not in text and "/members/dhnyu/" not in text
    for control in ("caseSelect", "resetZoom", "rasterVar", "rasterMode", "search", "profileFilter"):
        assert f'id="{control}"' in text
    for section in ("Vector transformation", "Raster transformation", "Attribute transformation"):
        assert section in text


def test_html_generation_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    write_html(first)
    write_html(second)
    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest()


def test_html_validation_rejects_external_and_absolute_paths(tmp_path: Path) -> None:
    output = tmp_path / "bad.html"
    write_html(output)
    output.write_text(output.read_text() + "https://example.invalid /mnt/hdd002/private", encoding="utf-8")
    with pytest.raises(InspectorError, match="external=True"):
        validate_html(output)


def test_html_escapes_malformed_payload_text(tmp_path: Path) -> None:
    payload = minimal_payload()
    payload["cases"][0]["reason"] = "</script><script>alert('x')</script>"
    output = tmp_path / "escaped.html"
    encoded = canonical_json(payload).decode().replace("<", "\\u003c")
    output.write_text(_template(encoded), encoding="utf-8")
    assert "</script><script>alert" not in output.read_text()
    assert "\\u003c/script>" in output.read_text()


def test_candidate_checksum_is_order_and_binary_explicit() -> None:
    tables = {"geometry": [{"candidate_id": "c", "geometry_wkb": b"\x01\x02"}], "attributes": []}
    value = _candidate_slice_checksum(tables)
    assert value == _candidate_slice_checksum({"attributes": [], "geometry": tables["geometry"]})
    changed = {"geometry": [{"candidate_id": "c", "geometry_wkb": b"\x01\x03"}], "attributes": []}
    assert value != _candidate_slice_checksum(changed)


def test_normalization_separates_nonfinite_and_binary() -> None:
    assert _normalize(float("nan")) is None
    assert _normalize(float("inf")) is None
    assert _normalize(b"\x00\xff") == "00ff"


@pytest.fixture(scope="module")
def accepted() -> AcceptedArtifacts:
    root = Path("/mnt/hdd002/dhnyu/fusedata/scene_data/reduced")
    if not root.is_dir():
        pytest.skip("accepted P3/P4 artifacts are unavailable")
    return AcceptedArtifacts(ROOT)


def test_real_manifests_and_indexes_resolve(accepted: AcceptedArtifacts) -> None:
    assert accepted.p3_manifest["cache_id"] == EXPECTED["p3_cache"]
    assert accepted.p4_acceptance["bank_id"] == EXPECTED["p4_bank"]
    assert accepted.index_manifest["index_id"] == EXPECTED["p4_index"]
    assert len(accepted.p3_rows) == 4421
    assert len(accepted.logical_rows) == 116208
    assert len(accepted.branch_by_scene) == 2421 * 3


def test_real_explicit_lookup_aligns_three_profiles(accepted: AcceptedArtifacts) -> None:
    scene_id = min(key[1] for key in accepted.logical_rows)
    accepted.validate_scene_view(scene_id, 0)
    candidate_ids = [accepted.logical_rows[(profile, scene_id, 0)]["candidate_id"] for profile in ("weak_0.5x", "main_1.0x", "strong_2.0x")]
    assert len(set(candidate_ids)) == 3
    for profile in ("weak_0.5x", "main_1.0x", "strong_2.0x"):
        path, manifest = accepted.p4_tar(profile, scene_id, verify=False)
        assert path.is_file() and scene_id in manifest["scene_ids"]


def test_rejects_invalid_view_and_nontraining_scene(accepted: AcceptedArtifacts) -> None:
    training_scene = min(key[1] for key in accepted.logical_rows)
    with pytest.raises(InspectorError, match=r"\[0, 15\]"):
        accepted.validate_scene_view(training_scene, 16)
    nontraining = next(scene for scene in sorted(accepted.p3_rows) if all((profile, scene, 0) not in accepted.logical_rows for profile in ("weak_0.5x", "main_1.0x", "strong_2.0x")))
    with pytest.raises(InspectorError, match="not an accepted P4 training scene"):
        accepted.validate_scene_view(nontraining, 0)


def test_reader_source_contains_no_writer_or_augmentation_call() -> None:
    source = (ROOT / "tools/augmentation_inspector/inspector.py").read_text()
    assert "augment_scene(" not in source
    assert "build_branch(" not in source
    assert "tar_make" not in source
    assert "write_parquet" not in source


def test_cli_import_has_no_side_effects() -> None:
    path = ROOT / "tools/render_augmentation_inspector.py"
    spec = importlib.util.spec_from_file_location("render_augmentation_inspector", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_read_only_contract_does_not_open_artifact_for_write() -> None:
    source = (ROOT / "tools/augmentation_inspector/inspector.py").read_text()
    forbidden = ("p3_root.write", "p4_root.write", "open(\"wb\")", "open('wb')")
    assert not any(token in source for token in forbidden)
