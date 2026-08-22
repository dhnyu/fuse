import json
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_i24_contract_is_zero_compute_and_lineage_locked():
    config = yaml.safe_load((ROOT / "config/prototype_model_acceptance.yml").read_text())
    assert config["scientific"]["gate_mode"] == "read_only_zero_compute"
    assert config["identity"]["model_validation_id"] == "pmv_1d5412a7b035635a4187fbf6"
    assert config["identity"]["best_checkpoint_sha256"] == "a17477a647d68024cb59ce6c3ce66a703e12143f37340b90c82cd3549b303704"
    assert config["scientific"]["retrieval"]["original_relevance_metrics"] == "forbidden"


def test_i24_schema_rejects_nonzero_compute(tmp_path):
    schema = json.loads((ROOT / "config/schemas/prototype_model_acceptance.schema.json").read_text())
    instance = {
        "schema_version": "1.0.0", "status": "PASS", "model_acceptance_id": "pma_" + "0" * 24,
        "direct_parents": [], "forwarded_lineage": [],
        "checkpoint": {"name": "epoch-005.pt", "path": "/x", "size_bytes": 1,
                       "sha256": "a17477a647d68024cb59ce6c3ce66a703e12143f37340b90c82cd3549b303704",
                       "epoch": 5, "optimizer_step": 40, "read_only": True},
        "gates": {}, "contracts": {}, "zero_compute": {
            "status": "PASS", "additional_optimizer_steps": 1, "forward_calls": 0,
            "augmentation_calls": 0, "state_update_calls": 0,
            "checkpoint_sha256_before": "0" * 64, "checkpoint_sha256_after": "0" * 64},
        "scientific_identity": {}, "immutable_publication": {
            "atomic": "PASS", "identical_rebuild_reuse": "PASS",
            "same_id_different_content_hard_failure": "PASS"}, "outputs": []}
    try:
        jsonschema.validate(instance, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("schema accepted a nonzero optimizer-step count")
