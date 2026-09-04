from __future__ import annotations

import copy
import importlib.metadata
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from jsonschema import Draft202012Validator

from p10_evaluation import (
    MODEL_IDS, P10Error, _metric, load_contract, make_analysis_contract,
    make_consumption, make_qualitative_contract, record_interrupted_execution,
    _installed_versions,
)
from p10_prepared_input import (
    CONTRACT_VERSION, P10PreparedInputError, make_cache_plan,
    validate_geometry_cache, validate_prepared_cache,
)
from p9_v2_canonical import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]


def contract():
    return load_contract(ROOT / "config/p10_evaluation.yml")


def galleries():
    return [{"scene_id": f"scn_{index:04d}"} for index in range(1600)]


def test_runtime_schema_is_draft_2020_12_and_contract_valid():
    schema = json.loads((ROOT / "config/schemas/p10_evaluation.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(yaml.safe_load((ROOT / "config/p10_evaluation.yml").read_text()))


def test_model_set_is_closed_ordered_eight():
    value = contract()
    assert tuple(row["configuration_id"] for row in value["model_set"]) == MODEL_IDS
    bad = copy.deepcopy(value); bad["model_set"] = bad["model_set"][:-1]
    path = ROOT / "tests" / ".never-written.yml"
    assert len(bad["model_set"]) == 7 and not path.exists()


def test_qualitative_contract_is_deterministic_unique_and_content_bound():
    first = make_qualitative_contract(contract(), galleries())
    second = make_qualitative_contract(contract(), galleries())
    assert first == second
    assert len(first["selected_scene_ids"]) == len(set(first["selected_scene_ids"])) == 10
    assert first["standard_candidate_count"] == 1599
    changed = galleries(); changed[-1] = {"scene_id": "scn_9999"}
    assert make_qualitative_contract(contract(), changed)["contract_id"] != first["contract_id"]


def test_qualitative_rejects_noncanonical_population_order():
    value = galleries(); value.reverse()
    with pytest.raises(P10Error, match="POPULATION_INVALID"):
        make_qualitative_contract(contract(), value)


def test_analysis_contract_freezes_umap_and_original_space_hdbscan():
    value = make_analysis_contract(contract())
    assert value["umap"]["random_state"] == 20260904
    assert value["hdbscan"]["min_cluster_size"] == 30
    assert value["hdbscan"]["metric"] == "euclidean"


def test_retrieval_metrics_known_ranks_and_counts():
    gallery = torch.eye(3)
    queries = torch.stack((gallery[0], gallery[0], gallery[1], gallery[1], gallery[2], gallery[2]))
    metrics, ranks = _metric(queries, gallery, 0.1)
    assert metrics["query_count"] == 6 and metrics["gallery_count"] == 3
    assert metrics["MRR"] == metrics["HIT@1"] == metrics["HIT@5"] == metrics["HIT@10"] == 1.0
    assert np.all(ranks[:, 0] == np.repeat(np.arange(3), 2))


def test_consumption_requires_all_eight_validation_gates():
    authority = {"authority_id": "p10auth_" + "a" * 24,
                 "models": [{"acceptance_id": f"p9accv2_{i:024x}"} for i in range(8)]}
    valid = [{"status": "PASS", "configuration_id": name} for name in MODEL_IDS]
    result = make_consumption(authority, valid, contract())
    assert result["transition"] == {"before": 0, "after": 1}
    with pytest.raises(P10Error, match="PREHELDOUT_GATE_INCOMPLETE"):
        make_consumption(authority, valid[:-1], contract())
    bad = copy.deepcopy(valid); bad[3]["status"] = "BLOCKED"
    with pytest.raises(P10Error, match="PREHELDOUT_GATE_INCOMPLETE"):
        make_consumption(authority, bad, contract())


def test_no_training_or_checkpoint_mutation_permissions():
    value = contract()
    assert value["execution"]["optimizer_updates"] == 0
    assert value["execution"]["checkpoint_writes"] == 0
    source = (ROOT / "python/p10_evaluation.py").read_text()
    for prohibited in ("optimizer.step(", ".backward(", "save_checkpoint(", "publish_acceptance("):
        assert prohibited not in source


def test_prepared_cache_plan_is_deterministic_and_complete():
    first = make_cache_plan(contract())
    second = make_cache_plan(contract())
    assert first == second
    assert first["contract_version"] == CONTRACT_VERSION
    assert first["cache_id"].startswith("p10pi_")
    assert len(first["ordered_records"]) == 6000
    assert len(first["source_inventory"]["validation_scene_ids"]) == 400
    assert len(first["source_inventory"]["evaluation_scene_ids"]) == 1600
    assert len(first["source_inventory"]["p5_query_sources"]) == 3200
    assert "p9_prepared_cache_plan" in first["source_inventory"]["files"]
    assert [row["role"] for row in first["ordered_records"][:2]] == ["validation_query"] * 2


def test_prepared_execution_environment_is_exactly_pinned():
    expected = contract()["prepared_input"]["environment"]
    assert _installed_versions() == expected
    assert expected["scikit-learn"] == "1.7.2"
    assert importlib.metadata.version("hdbscan") == "0.8.40"


def test_formal_evaluation_has_no_dynamic_input_fallback():
    source = (ROOT / "python/p10_evaluation.py").read_text()
    body = source[source.index("def evaluate_model("):source.index("def _installed_versions(")]
    assert "_embed_prepared(" in body
    assert "_dynamic_catalog(" not in body
    assert "prepared_cache: P10PreparedInputCache" in body


def test_reexecution_reuses_closed_authority_and_consumption():
    value = contract()["reexecution"]
    assert value == {
        "authority_id": "p10auth_8b6919578aaa24fa8f1b98a2",
        "consumption_id": "p10cons_7d0eba832b70d545fc5d3eb4",
        "interruption_reason": "OPERATOR_REQUESTED_PERFORMANCE_REMEDIATION_P10_INPUT_PIPELINE",
        "interrupted_tmux_session": "p10_model_shards_20260904",
        "interrupted_completed_models": ["cmp_ssv_like", "cmp_ds_like"],
    }
    cli = (ROOT / "scripts/p10_evaluation.py").read_text()
    assert "only the bound --reexecute path is allowed" in cli


def test_interruption_record_binds_existing_consumption_and_completed_outputs(tmp_path):
    value = copy.deepcopy(contract())
    source = Path(value["publication_root"])
    destination = tmp_path / "canonical"
    value["publication_root"] = str(destination)
    authority_id = value["reexecution"]["authority_id"]
    consumption_id = value["reexecution"]["consumption_id"]
    copies = [
        (source / "authorities" / f"{authority_id}.json",
         destination / "authorities" / f"{authority_id}.json"),
        (source / "consumption" / f"{consumption_id}.json",
         destination / "consumption" / f"{consumption_id}.json"),
    ]
    for configuration_id in value["reexecution"]["interrupted_completed_models"]:
        relative = Path("evaluations") / authority_id / configuration_id / "evaluation.json"
        copies.append((source / relative, destination / relative))
    for original, copied in copies:
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copied)
    result = record_interrupted_execution(value)
    assert result["reason"] == "OPERATOR_REQUESTED_PERFORMANCE_REMEDIATION_P10_INPUT_PIPELINE"
    assert result["status"] == "INTERRUPTED_PRESERVED"
    assert result["consumption_id"] == consumption_id
    assert [item["configuration_id"] for item in result["completed_model_evaluations"]] == [
        "cmp_ssv_like", "cmp_ds_like"
    ]
    assert (destination / "interruptions" / f"{result['interruption_id']}.json").is_file()


def _published_cache_paths():
    value = contract()
    plan = make_cache_plan(value)
    prepared = Path(value["prepared_input"]["root"]) / plan["cache_id"] / "prepared_input_manifest.json"
    geometries = sorted(Path(value["prepared_input"]["geometry_root"]).glob("p10geo_*/prepared_geometry_manifest.json"))
    return prepared, geometries


def test_published_prepared_cache_rejects_stale_missing_and_corrupt_payload(tmp_path):
    prepared, _ = _published_cache_paths()
    if not prepared.is_file():
        pytest.skip("production prepared cache has not been materialized")
    manifest = validate_prepared_cache(prepared, verify_payloads=False)

    stale = copy.deepcopy(manifest)
    stale["plan"]["contract_version"] = "stale-contract"
    stale_path = tmp_path / "stale.json"
    stale_path.write_text(json.dumps(stale))
    with pytest.raises(P10PreparedInputError, match="PREPARED_MANIFEST_IDENTITY_INVALID"):
        validate_prepared_cache(stale_path, verify_payloads=False)

    missing_path = tmp_path / "missing" / "prepared_input_manifest.json"
    missing_path.parent.mkdir()
    missing_path.write_text(json.dumps(manifest))
    with pytest.raises(P10PreparedInputError, match="PREPARED_PAYLOAD_MISSING"):
        validate_prepared_cache(missing_path, verify_payloads=True)

    corrupt = copy.deepcopy(manifest)
    first = corrupt["batches"][0]
    first["payload_sha256"] = "0" * 64
    corrupt["manifest_sha256"] = canonical_sha256(
        {key: value for key, value in corrupt.items() if key != "manifest_sha256"}
    )
    corrupt_path = tmp_path / "corrupt" / "prepared_input_manifest.json"
    source = prepared.parent / first["relative_path"]
    destination = corrupt_path.parent / first["relative_path"]
    destination.parent.mkdir(parents=True)
    shutil.copyfile(source, destination)
    corrupt_path.write_text(json.dumps(corrupt))
    with pytest.raises(P10PreparedInputError, match="PREPARED_PAYLOAD_HASH_MISMATCH"):
        validate_prepared_cache(corrupt_path, verify_payloads=True)


def test_published_geometry_cache_rejects_missing_payload(tmp_path):
    _, geometries = _published_cache_paths()
    if not geometries:
        pytest.skip("production prepared geometry cache has not been materialized")
    manifest = validate_geometry_cache(geometries[-1], verify_payloads=False)
    copied = tmp_path / "prepared_geometry_manifest.json"
    copied.write_text(json.dumps(manifest))
    with pytest.raises(P10PreparedInputError, match="PREPARED_GEOMETRY_PAYLOAD_MISSING"):
        validate_geometry_cache(copied, verify_payloads=True)
