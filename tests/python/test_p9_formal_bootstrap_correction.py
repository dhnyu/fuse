from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from p6_data import VOCABULARY_FIELDS, build_vocabulary, validate_vocabulary_contract
from p9_formal_execution import (FormalAttemptLock, failed_state_payload,
                                 validate_terminal_state_consistency)
from p9_formal_training import _rank_failures, model_state
from p9_model_families import FAMILY_NAMES, P9FM64Encoder, build_scene_encoder


CATEGORIES = Path(yaml.safe_load((ROOT / "config/p9_formal_isolated_runtime.yml").read_text())["roots"]["categories"]["path"])


def canonical_vocabulary():
    return build_vocabulary(CATEGORIES)


def identity():
    return {"duplicate_key": "a" * 64, "attempt_id": "p9attempt_fixture",
            "run_id": "p9run_fixture", "reservation_id": "p9res_fixture",
            "authority_id": "p9a_fixture", "actual_launch_commit": "b" * 40,
            "runtime_tree_sha256": "c" * 64, "world_size": 2}


def test_canonical_vocabulary_is_a_direct_strict_field_mapping():
    vocabulary = canonical_vocabulary(); sizes = validate_vocabulary_contract(vocabulary)
    assert set(vocabulary) == VOCABULARY_FIELDS == set(sizes)
    assert all(sizes[name] == vocabulary[name]["size"] for name in sizes)
    assert all(vocabulary[name]["missing"] == len(vocabulary[name]["keys"]) for name in sizes)
    assert all(vocabulary[name]["mask"] == len(vocabulary[name]["keys"]) + 1 for name in sizes)
    assert "fields" not in vocabulary


@pytest.mark.parametrize("mutation,match", [
    (lambda value: {"fields": value}, "field mismatch"),
    (lambda value: {key: row for key, row in value.items() if key != "A9"}, "field mismatch"),
    (lambda value: {**value, "A9": {**value["A9"], "size": 0}}, "invalid vocabulary size"),
    (lambda value: {**value, "A9": {**value["A9"], "mapping": {"bad": value["A9"]["size"]}}}, "out-of-range"),
])
def test_invalid_vocabulary_contracts_fail_closed(mutation, match):
    with pytest.raises(ValueError, match=match):
        validate_vocabulary_contract(mutation(copy.deepcopy(canonical_vocabulary())))


@pytest.mark.parametrize("dimension", [48, 64, 128])
@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_every_family_and_dimension_consumes_canonical_sizes(family, dimension):
    config = yaml.safe_load((ROOT / "config/p6_model_dataloader.yml").read_text())
    config["model"].update({"d": dimension, "d_c": dimension, "head_dimension": dimension // 4,
                            "ffn_dimension": dimension * 2})
    model = build_scene_encoder(config, validate_vocabulary_contract(canonical_vocabulary()), family)
    assert sum(parameter.numel() for parameter in model.parameters()) > 0


def test_cfg_main_uses_byte_compatible_p7_parameter_namespace_with_p9_interface():
    config = yaml.safe_load((ROOT / "config/p6_model_dataloader.yml").read_text())
    model = build_scene_encoder(config, validate_vocabulary_contract(canonical_vocabulary()), "FM")
    assert isinstance(model, P9FM64Encoder)
    assert model.contract.name == "FM"
    assert all(not name.startswith("encoder.") for name in model.state_dict())


@pytest.mark.parametrize("rank_case", ["rank_0", "rank_1", "both"])
def test_rank_failure_collection_is_deterministic(tmp_path, rank_case):
    ranks = (0,) if rank_case == "rank_0" else (1,) if rank_case == "rank_1" else (0, 1)
    for rank in ranks:
        (tmp_path / f"rank_failure_{rank}.json").write_text(json.dumps({
            "rank": rank, "exit_code": 1, "failure_stage": "MODEL_CONSTRUCTION",
            "failure_class": "RuntimeError", "failure_message": f"rank {rank}",
            "traceback_sha256": str(rank) * 64, "process_group_cleanup_status": "CONFIRMED"}))
    codes, stage, failure_class, message = _rank_failures(tmp_path, 1)
    assert set(codes) == {f"rank_{rank}" for rank in ranks}
    assert stage == "MODEL_CONSTRUCTION" and failure_class == "RuntimeError"
    assert all(f"rank {rank}" in message for rank in ranks)


@pytest.mark.parametrize("stage", [
    "VOCABULARY_LOADING", "AFTER_DDP_INITIALIZATION", "MODEL_CONSTRUCTION",
    "OPTIMIZER_SCHEDULER_QUEUE_CONSTRUCTION", "FIRST_BATCH_LOADING", "FORWARD", "BACKWARD_PRE_STEP",
])
def test_failure_stages_publish_nonresumable_zero_update_state(tmp_path, stage):
    lock = FormalAttemptLock(tmp_path / "locks", identity()); lock.acquire()
    state = failed_state_payload(identity(), failure_stage=stage, failure_class="InjectedFailure",
        failure_message="synthetic non-formal failure", traceback_sha256="d" * 64,
        rank_exit_codes={"rank_0": 1, "rank_1": 1}, started_unix=1.0,
        failed_unix=2.0, process_group_cleanup="CONFIRMED")
    state_path = tmp_path / "attempt_state.json"
    from p9_formal_execution import atomic_json
    atomic_json(state_path, state); lock.heartbeat("FAILED_NONRESUMABLE")
    lock.release_terminal("FAILED_NONRESUMABLE"); state["lock_release_status"] = "RELEASED"
    atomic_json(state_path, state)
    validate_terminal_state_consistency(state, json.loads(lock.owner_path.read_text()),
                                        json.loads(lock.heartbeat_path.read_text()))
    schema = json.loads((ROOT / "config/schemas/p9_formal_failed_state.schema.json").read_text())
    jsonschema.validate(state, schema)
    assert state["optimizer_updates"] == 0 and not state["resume_eligible"]
    assert lock.stream is None


def test_state_disagreement_is_detected():
    state = failed_state_payload(identity(), failure_stage="MODEL_CONSTRUCTION",
        failure_class="RuntimeError", failure_message="failure", traceback_sha256="d" * 64,
        rank_exit_codes={"rank_0": 1}, started_unix=1.0)
    state["lock_release_status"] = "RELEASED"
    owner = {**identity(), "state": "FAILED_NONRESUMABLE", "terminal_state": "FAILED_NONRESUMABLE"}
    heartbeat = {"state": "RUNNING"}
    with pytest.raises(ValueError, match="heartbeat"):
        validate_terminal_state_consistency(state, owner, heartbeat)


def test_formal_model_state_uses_canonical_sizes_not_obsolete_wrapper(monkeypatch):
    source = (ROOT / "scripts/p9_formal_training.py").read_text()
    assert 'vocabulary["fields"]' not in source and 'value["values"]' not in source
    assert 'vocabulary["masks"]' not in source
    assert 'contract["mask"]' in source
    assert "validate_vocabulary_contract" in source
    assert "destroy_process_group()" in source and "finally:" in source


def test_formal_model_state_uses_canonical_queue_contract():
    source = (ROOT / "scripts/p9_formal_training.py").read_text()
    assert 'empty_queue(device, capacity=capacity, dimension=dimension)' in source
    assert 'empty_queue(values["config"], device)' not in source


def test_formal_launch_uses_accepted_nccl_transport_and_explicit_device():
    source = (ROOT / "scripts/p9_formal_training.py").read_text()
    assert '"NCCL_P2P_DISABLE": "1"' in source
    assert '"NCCL_IB_DISABLE": "1"' in source
    assert source.count('env=formal_launch_environment(values)') == 2
    assert source.count('init_process_group("nccl", device_id=device)') == 2


def test_formal_runner_opens_the_accepted_geometry_manifest():
    source = (ROOT / "scripts/p9_formal_training.py").read_text()
    assert source.count('"geometry" / "geometry_cache_manifest.json"') == 2
    assert 'GeometryCacheReader(Path(args.cache_root) / "geometry",' not in source


def test_formal_reader_validates_the_canonical_prepared_payload_envelope():
    source = (ROOT / "scripts/p9_formal_training.py").read_text()
    assert 'payload.get("global_index", -1)' in source
    assert 'payload.get("spec") != spec' in source
    assert 'payload["index"]' not in source
