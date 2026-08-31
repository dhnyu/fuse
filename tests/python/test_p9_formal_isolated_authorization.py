from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import canonical_json_bytes
from p9_formal_isolated_authorization import _validate_root, artifact, atomic_publish


def test_isolated_root_validation_is_byte_sensitive(tmp_path):
    path = tmp_path / "root.json"
    path.write_bytes(canonical_json_bytes({"schema_version": "1.0.0", "status": "PASS", "thing_id": "id"}))
    import hashlib
    spec = {"path": str(path), "artifact_type": "fixture", "identity_field": "thing_id",
            "expected_identity": "id", "expected_size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    assert _validate_root("fixture", spec)["immutability_status"] == "ACCEPTED_IMMUTABLE_INPUT"
    path.write_text("mutated")
    with pytest.raises(ValueError, match="size mismatch"):
        _validate_root("fixture", spec)


def test_isolated_artifact_identity_and_publication_are_deterministic(tmp_path):
    first = artifact("p9x_", "fixture", {"status": "PASS", "value": 1}, "fixture_id")
    second = artifact("p9x_", "fixture", {"status": "PASS", "value": 1}, "fixture_id")
    assert first == second
    paths = atomic_publish(tmp_path / "publication", {"fixture": first})
    before = paths[0].stat().st_mtime_ns
    assert atomic_publish(tmp_path / "publication", {"fixture": second}) == paths
    assert paths[0].stat().st_mtime_ns == before
    changed = artifact("p9x_", "fixture", {"status": "PASS", "value": 2}, "fixture_id")
    with pytest.raises(FileExistsError, match="collision"):
        atomic_publish(tmp_path / "publication", {"fixture": changed})


def test_isolated_pipeline_never_imports_main_target_list():
    script = (ROOT / "_targets_p9_formal.R").read_text()
    declarations = (ROOT / "targets/research_p9_formal_execution.R").read_text()
    assert 'source("_targets.R")' not in script
    assert "list_p9_formal_execution" in script
    forbidden = ("p9_production_cache_materialization", "hyperparameter_configuration_matrix",
                 "p7_cold_path_runtime_acceptance", "tar_cue(mode = \"never\")")
    assert all(value not in declarations for value in forbidden)
