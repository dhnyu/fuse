from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.append(str(ROOT / "scripts"))

from artifact_protocol import canonical_sha256
from training_campaign import (
    COMPARISON_IDS, cache_identity, canonical_selection, comparison_authorities,
    current_lineage, ofat_authorities,
    scientific_configuration, scientific_implementation_hash, select_ofat_winner,
    selection_hash, s08_selection_document,
    validate_current_results, validate_current_winner,
    ordered_comparisons,
)
from training_controller import TrainingControllerError, training_run_id
from training_finalization import selection_contract_content
from training_runtime_provenance import runtime_implementation_provenance, runtime_source_paths
from training_transport import gpu_pair_environment
from prepare_training_cache import validate_cache

PLAN_PATH = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan/current_cbb824f19be83552/current_experiment_plan.json")


def values():
    plan = json.loads(PLAN_PATH.read_text())
    contract = yaml.safe_load((ROOT / "config/training_controller.yml").read_text())
    training = yaml.safe_load((ROOT / "config/training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/model_inputs.yml").read_text())
    lineage = current_lineage(plan, contract)
    parents = {**lineage, "production_cache_id": "s09cache_fixture",
               "production_cache_acceptance_id": "s09ca_fixture",
               "retirement_id": contract["parents"]["retirement_id"]}
    return plan, contract, training, model, parents


def results(authorities):
    return [{"configuration_id": authority["content"]["scientific"]["configuration_id"],
             "authority_id": authority["identity"],
             "phase": authority["content"]["scientific"]["phase"],
             "model_id": authority["content"]["scientific"]["model_id"],
             "status": "PASS", "checkpoint_id": f"p9ck_{index:024x}",
             "validation_retrieval_loss": 1.0 + index / 100,
             "mean_source_separation_margin": 0.1, "completed_epoch": 5}
            for index, authority in enumerate(authorities)]


def test_current_lineage_has_no_placeholder_and_stale_parent_fails():
    plan, contract, *_ = values(); assert len(current_lineage(plan, contract)) == 8
    changed = copy.deepcopy(contract); changed["parents"]["dataset_acceptance_id"] = "old"
    with pytest.raises(TrainingControllerError, match="LINEAGE_MISMATCH"): current_lineage(plan, changed)
    changed = copy.deepcopy(contract); changed["source"]["scientific_revision_token"] = "mrev_" + "0" * 16
    with pytest.raises(TrainingControllerError, match="LINEAGE_MISMATCH"): current_lineage(plan, changed)


def test_selection_is_exactly_s08_and_minimum_delta_is_bound():
    plan, *_ = values()
    assert canonical_selection(plan) == {**selection_contract_content(), "minimum_delta": 0.0001}
    assert selection_hash(plan) == canonical_sha256(plan["selection_protocol"])
    assert s08_selection_document(plan)["content_sha256"] == selection_hash(plan)
    changed = copy.deepcopy(plan); changed["selection_protocol"]["minimum_delta"] = 0.001
    with pytest.raises(TrainingControllerError, match="SELECTION_CONTRACT_MISMATCH"): canonical_selection(changed)


def test_ofat_authorities_are_exact_deterministic_and_current():
    plan, _, training, model, parents = values(); implementation = scientific_implementation_hash(ROOT)
    first = ofat_authorities(plan, training, model, parents, implementation)
    assert first == ofat_authorities(plan, training, model, parents, implementation) and len(first) == 11
    assert len({item["identity"] for item in first}) == 11
    assert first[0]["content"]["scientific"]["configuration_hash"] == canonical_sha256(
        scientific_configuration(plan["hyperparameter_configurations"][0], "FM"))
    changed = copy.deepcopy(parents); changed["experiment_plan_id"] = "old-plan"
    assert training_run_id(ofat_authorities(plan, training, model, changed, implementation)[0]) != training_run_id(first[0])


def test_s09_authority_identity_retains_runtime_implementation_provenance():
    plan, _, training, model, parents = values()
    first = ofat_authorities(plan, training, model, parents, "a" * 64)[0]
    second = ofat_authorities(plan, training, model, parents, "b" * 64)[0]
    assert first["content"]["scientific"]["scientific_implementation_hash"] == "a" * 64
    assert second["content"]["scientific"]["scientific_implementation_hash"] == "b" * 64
    assert first["identity"] != second["identity"]
    assert training_run_id(first) != training_run_id(second)


def test_runtime_provenance_registry_is_canonical_and_current():
    provenance = runtime_implementation_provenance(ROOT)
    registered = tuple(path.relative_to(ROOT).as_posix() for path in runtime_source_paths(ROOT))
    assert registered == tuple(provenance["source_hashes"])
    assert provenance["implementation_sha256"] == scientific_implementation_hash(ROOT)
    assert provenance["implementation_sha256"] != (
        "0479d8ae41fb22a4c3c2f82360fa2d12cd0f59fd73d8a50ef0868d2eff1cf66d")
    assert {"python/training_family_inputs.py", "python/training_prepared_cache.py"} <= set(registered)
    assert tuple(provenance["authority_source_hashes"]) == (
        "python/training_campaign.py", "scripts/training_campaign.py")


def test_runtime_hash_changes_all_authority_ids_but_not_plan_or_cache():
    plan, _, training, model, parents = values()
    first_ofat = ofat_authorities(plan, training, model, parents, "a" * 64)
    second_ofat = ofat_authorities(plan, training, model, parents, "b" * 64)
    winner_a = select_ofat_winner(plan, results(first_ofat))
    winner_b = select_ofat_winner(plan, results(second_ofat))
    first_comparisons = comparison_authorities(plan, winner_a, training, model, parents, "a" * 64)
    second_comparisons = comparison_authorities(plan, winner_b, training, model, parents, "b" * 64)
    assert all(a["identity"] != b["identity"] for a, b in zip(first_ofat, second_ofat))
    assert all(a["identity"] != b["identity"] for a, b in zip(first_comparisons, second_comparisons))
    assert plan["plan_id"] == "s08plan_7cd58ffb65db3d43fd3fa234"
    assert parents["production_cache_id"] == "s09cache_fixture"
    assert parents["production_cache_acceptance_id"] == "s09ca_fixture"


def test_winner_requires_all_results_and_uses_strict_selection():
    plan, _, training, model, parents = values()
    authorities = ofat_authorities(plan, training, model, parents, scientific_implementation_hash(ROOT))
    rows = results(authorities); rows[1]["validation_retrieval_loss"] = rows[0]["validation_retrieval_loss"] + 0.00005
    rows[1]["mean_source_separation_margin"] = 0.2
    assert select_ofat_winner(plan, rows)["selected_configuration_id"] == rows[1]["configuration_id"]
    with pytest.raises(TrainingControllerError, match="INCOMPLETE"): select_ofat_winner(plan, rows[:-1])


def test_new_campaign_rejects_every_historical_authority_and_winner():
    plan, _, training, model, parents = values()
    old = ofat_authorities(plan, training, model, parents, "a" * 64)
    new = ofat_authorities(plan, training, model, parents, "b" * 64)
    validate_current_results(results(new), new)
    winner = select_ofat_winner(plan, results(new))
    validate_current_winner(plan, winner, new)
    with pytest.raises(TrainingControllerError, match="STALE"):
        validate_current_winner(plan, select_ofat_winner(plan, results(old)), new)
    old_cmp = comparison_authorities(plan, winner, training, model, parents, "a" * 64)
    new_cmp = comparison_authorities(plan, winner, training, model, parents, "b" * 64)
    validate_current_results(results(new_cmp), new_cmp)
    with pytest.raises(TrainingControllerError, match="STALE"):
        validate_current_results(results(old_cmp), new_cmp)


def test_comparison_authorities_require_winner_and_propagate_hyperparameters():
    plan, _, training, model, parents = values(); implementation = scientific_implementation_hash(ROOT)
    winner = select_ofat_winner(plan, results(ofat_authorities(plan, training, model, parents, implementation)))
    authorities = comparison_authorities(plan, winner, training, model, parents, implementation)
    assert len(authorities) == 17
    assert tuple(item["content"]["scientific"]["model_id"] for item in authorities) == COMPARISON_IDS
    selected = next(row for row in plan["hyperparameter_configurations"] if row["configuration_id"] == winner["selected_configuration_id"])
    assert all(item["content"]["scientific"]["hyperparameters"]["d"] == selected["d"] for item in authorities)
    expected = {**selected, "configuration_id": "cmp_FM"}
    assert authorities[0]["content"]["scientific"]["configuration_hash"] == canonical_sha256(
        scientific_configuration(expected, "FM"))
    with pytest.raises(TrainingControllerError, match="WINNER_REQUIRED"):
        comparison_authorities(plan, {"status": "FAILED"}, training, model, parents, implementation)


def test_dissertation_order_and_smoke_parity():
    import s09_smoke
    expected = ("FM", "A1", "A2", "A3", "A4", "A5", "SSV", "DS",
                "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9")
    assert COMPARISON_IDS == s09_smoke.COMPARISONS == expected
    assert len(set(COMPARISON_IDS)) == 17
    rows = [{"model_id": name} for name in reversed(expected)]
    assert tuple(r["model_id"] for r in ordered_comparisons(rows, "model_id")) == expected
    for invalid in (rows[:-1], rows + rows[:1], rows[:-1] + rows[:1]):
        with pytest.raises(TrainingControllerError, match="INVENTORY_INVALID"):
            ordered_comparisons(invalid, "model_id")


def test_order_does_not_change_authorities_seeds_or_science(monkeypatch):
    import training_campaign
    plan, _, training, model, parents = values()
    original = copy.deepcopy(plan)
    implementation = scientific_implementation_hash(ROOT)
    winner = select_ofat_winner(plan, results(ofat_authorities(plan, training, model, parents, implementation)))
    new = comparison_authorities(plan, winner, training, model, parents, implementation)
    legacy_order = tuple(row["name"] for row in plan["comparison_configurations"])
    with monkeypatch.context() as context:
        context.setattr(training_campaign, "COMPARISON_IDS", legacy_order)
        old = comparison_authorities(plan, winner, training, model, parents, implementation)
    by_model = lambda authorities: {a["content"]["scientific"]["model_id"]: a for a in authorities}
    assert by_model(new) == by_model(old)
    assert {training_run_id(a) for a in new} == {training_run_id(a) for a in old}
    assert plan == original
    shuffled = copy.deepcopy(plan)
    shuffled["comparison_configurations"].reverse()
    assert comparison_authorities(shuffled, winner, training, model, parents, implementation) == new
    with pytest.raises(TrainingControllerError, match="INCOMPLETE"):
        validate_current_results(results(new)[:-1], new)


def test_prepared_cache_identity_changes_with_parent_or_implementation():
    base = {"p3": "a", "cache_implementation_sha256": "b" * 64}; first = cache_identity(base, "c" * 64)
    assert first == cache_identity(base, "c" * 64)
    assert first != cache_identity({**base, "p3": "old"}, "c" * 64)
    assert first != cache_identity({**base, "cache_implementation_sha256": "d" * 64}, "c" * 64)


def test_authority_run_key_binds_cache_selection_phase_and_model():
    plan, _, training, model, parents = values()
    implementation = scientific_implementation_hash(ROOT)
    authority = ofat_authorities(plan, training, model, parents, implementation)[0]
    baseline = training_run_id(authority)
    for section, key, value in (
        ("scientific", "prepared_cache_id", "s09cache_other"),
        ("scientific", "selection_contract_hash", "0" * 64),
        ("scientific", "phase", "COMPARISON"),
        ("scientific", "model_id", "A1"),
    ):
        changed = copy.deepcopy(authority)
        changed["content"][section][key] = value
        changed["content"]["scientific_run_key"] = canonical_sha256({
            "scientific": changed["content"]["scientific"],
            "parents": changed["content"]["parents"],
            "parent_hashes": changed["content"]["parent_hashes"],
        })
        changed["content_sha256"] = canonical_sha256(changed["content"])
        changed["identity"] = "s09auth_" + changed["content_sha256"][:24]
        assert training_run_id(changed) != baseline


def test_gpu_pair_environment_requires_two_devices_and_holds_locks(tmp_path):
    execution = {
        "selected_gpu_indices": [0, 1], "world_size": 2, "backend": "nccl",
        "gpu_lock_root": str(tmp_path), "gpu_lock_timeout_seconds": 0.1,
        "transport": {"p2p_disable": "1", "ib_disable": "1",
                      "preflight_timeout_seconds": 30},
    }
    wrong = copy.deepcopy(execution); wrong["selected_gpu_indices"] = [0]
    with pytest.raises(TrainingControllerError, match="MUST_BE_0_1"):
        with gpu_pair_environment(wrong): pass
    with gpu_pair_environment(execution, {}) as environment:
        assert environment["CUDA_VISIBLE_DEVICES"] == "0,1"
        assert environment["NCCL_P2P_DISABLE"] == "1"
        assert environment["NCCL_IB_DISABLE"] == "1"
        with pytest.raises(TrainingControllerError, match="LOCK_UNAVAILABLE"):
            blocked = copy.deepcopy(execution); blocked["gpu_lock_timeout_seconds"] = 0
            with gpu_pair_environment(blocked): pass


def test_prepared_cache_acceptance_is_fail_closed(tmp_path):
    from artifact_protocol import canonical_json_bytes, sha256_file
    root = tmp_path / "cache"
    parents = {key: f"current-{key}" for key in (
        "methodology_authority_id", "experiment_plan_id", "dataset_acceptance_id",
        "query_acceptance_id", "bank_acceptance_id", "scene_cache_acceptance_id",
        "scene_cache_id", "scientific_revision_token")}
    parents["cache_implementation_sha256"] = "a" * 64
    membership = "b" * 64; cache_id, _ = cache_identity(parents, membership, 0)
    root = tmp_path / cache_id; root.mkdir()
    plan = {"entry_count": 0}; (root / "canonical_cache_plan.json").write_bytes(canonical_json_bytes(plan))
    scientific = {"schema_version": "1.0.0", "status": "PASS", "parents": parents,
                  "entry_count": 0, "membership_sha256": membership, "entries": []}
    digest = canonical_sha256(scientific)
    manifest = {**scientific, "content_sha256": digest, "cache_id": cache_id}
    (root / "production_cache_manifest.json").write_bytes(canonical_json_bytes(manifest))
    acceptance_content = {"schema_version": "1.0.0", "status": "PASS", "cache_id": cache_id,
                          "manifest_sha256": sha256_file(root / "production_cache_manifest.json"),
                          "parents": parents, "entry_count": 0, "optimizer_updates": 0,
                          "training_runs": 0, "fixture_only": True}
    acceptance_hash = canonical_sha256(acceptance_content)
    acceptance = {**acceptance_content, "acceptance_id": "s09ca_" + acceptance_hash[:24],
                  "content_sha256": acceptance_hash}
    (root / "acceptance.json").write_bytes(canonical_json_bytes(acceptance))
    assert validate_cache(root, verify_payloads=False)["cache_id"] == cache_id
    acceptance["cache_id"] = "stale"
    (root / "acceptance.json").write_bytes(canonical_json_bytes(acceptance))
    with pytest.raises(ValueError, match="cache|identity/acceptance"):
        validate_cache(root, verify_payloads=False)
