"""Safety tests for the bounded supplementary pilot entry point."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("retrieval_pilot", ROOT / "scripts/retrieval_gallery_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_pilot_cannot_overwrite_evidence(tmp_path):
    target = tmp_path / "evidence.json"
    pilot.write_new(target, {"status": "PASS"})
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        pilot.write_new(target, {"status": "FAIL"})
    assert target.read_bytes() == before


def test_frozen_supplementary_scope():
    cfg = yaml.safe_load((ROOT / "config/retrieval_gallery.yml").read_text())
    scientific = cfg["scientific"]
    assert scientific["canonical_evaluation_count"] == 1600
    assert scientific["supplemental_count"] == 8400
    assert scientific["union_count"] == 10000
    assert scientific["skip_accepted_positions"] == 2000
    assert scientific["candidate_batch_size"] == 8192
    assert scientific["model_scope"] == "accepted_eight_models"
    assert scientific["augmented_queries"] == scientific["downstream_targets"] == 0
    assert scientific["precision"] == "float32"
    assert not scientific["amp"] and not scientific["tf32"]
    assert cfg["execution"]["minimum_free_bytes"] >= 120 * 1024**3


def test_sampler_refuses_existing_directory():
    import subprocess
    result = subprocess.run(["Rscript", "-e", 'source("R/retrieval_gallery.R"); retrieval_sample("unused", ".")'],
                            cwd=ROOT, text=True, capture_output=True)
    assert result.returncode != 0
    assert "immutable output required" in result.stderr


@pytest.mark.parametrize("name", ["prototype_vector_observation", "prototype_raster_observation", "prototype_relation"])
def test_supplemental_schemas_change_only_identity_namespace(name):
    original = json.loads((ROOT / f"config/schemas/{name}.schema.json").read_text())
    supplemental = json.loads((ROOT / f"config/schemas/retrieval_gallery/{name}.schema.json").read_text())
    original.pop("$id", None)
    supplemental.pop("$id", None)

    def restore(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "split" and child == {"const": "retrieval_only"}:
                    value[key] = {"enum": ["training", "validation", "evaluation"]}
                else:
                    restore(child)
        elif isinstance(value, list):
            for child in value:
                restore(child)

    restore(supplemental)
    assert original == supplemental
