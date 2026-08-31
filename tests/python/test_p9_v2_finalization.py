from __future__ import annotations

import copy
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import build_run_bundle, publish_run_bundle  # noqa: E402
from p9_v2_bundle_test_support import make_bundle_fixture  # noqa: E402
from p9_v2_c_test_support import CandidateSpec, make_published_case  # noqa: E402
from p9_v2_canonical import canonical_sha256  # noqa: E402
from p9_v2_finalization import (  # noqa: E402
    finalize_run_bundle,
    make_selection_contract,
    validate_finalization_result,
)
from p9_v2_schema import P9V2SchemaError, validate_instance  # noqa: E402


def _simple(tmp_path: Path, terminal: str = "complete"):
    fixture = make_bundle_fixture(tmp_path / "fixture", terminal=terminal)
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    publication = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    return fixture, publication.path


@pytest.mark.parametrize(
    ("specs", "selected_index"),
    [
        ((CandidateSpec(5, 380, 0.5, 0.2), CandidateSpec(10, 760, 0.4, 0.1)), 1),
        ((CandidateSpec(5, 380, 0.5, 0.2), CandidateSpec(10, 760, 0.50005, 0.3)), 1),
        ((CandidateSpec(5, 380, 0.5, 0.2), CandidateSpec(10, 760, 0.5, 0.2)), 0),
        ((CandidateSpec(5, 380, 0.0001, 0.3), CandidateSpec(10, 760, 0.0, 0.1)), 1),
    ],
)
def test_selection_rule_matrix(tmp_path, specs, selected_index):
    case = make_published_case(tmp_path, specs)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "SUCCEEDED"
    assert result["selected_checkpoint"]["completed_epoch"] == specs[selected_index].epoch


def test_early_stopping_patience_four(tmp_path):
    specs = tuple(CandidateSpec(epoch, epoch * 76, 0.4 if epoch == 5 else 0.5, 0.2) for epoch in (5, 10, 15, 20, 25))
    case = make_published_case(tmp_path, specs)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "SUCCEEDED"
    assert result["stopping_summary"]["patience_reached"] is True
    assert result["stopping_summary"]["completed_epoch"] == 25
    assert result["selector_replay_summary"]["final_events_without_improvement"] == 4


def test_margin_tiebreak_selects_checkpoint_without_resetting_patience(tmp_path):
    specs = (
        CandidateSpec(5, 380, 0.5, 0.1),
        CandidateSpec(10, 760, 0.50005, 0.2),
        CandidateSpec(15, 1140, 0.6, 0.3),
        CandidateSpec(20, 1520, 0.6, 0.3),
        CandidateSpec(25, 1900, 0.6, 0.3),
    )
    case = make_published_case(tmp_path, specs)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "SUCCEEDED"
    assert result["selected_checkpoint"]["completed_epoch"] == 10
    assert result["selector_replay_summary"]["steps"][1]["selected_as_best"] is True
    assert result["selector_replay_summary"]["steps"][1]["patience_reset"] is False
    assert result["selector_replay_summary"]["final_events_without_improvement"] == 4
    assert result["stopping_summary"]["completed_epoch"] == 25


def test_loss_improvement_crossing_tolerance_resets_patience(tmp_path):
    specs = (
        CandidateSpec(5, 380, 0.5, 0.1),
        CandidateSpec(10, 760, math.nextafter(0.5 - 0.0001, -math.inf), 0.0),
    )
    case = make_published_case(tmp_path, specs)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "SUCCEEDED"
    assert result["selector_replay_summary"]["steps"][1]["selected_as_best"] is True
    assert result["selector_replay_summary"]["steps"][1]["patience_reset"] is True
    assert result["selector_replay_summary"]["final_events_without_improvement"] == 0


def test_exactly_before_patience_is_complete_without_early_stop(tmp_path):
    specs = tuple(CandidateSpec(epoch, epoch * 76, 0.4 if epoch == 5 else 0.5, 0.2) for epoch in (5, 10, 15, 20))
    case = make_published_case(tmp_path, specs)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "SUCCEEDED"
    assert result["stopping_summary"]["patience_reached"] is False
    assert result["selector_replay_summary"]["final_events_without_improvement"] == 3


def test_candidate_after_stopping_boundary_is_rejected(tmp_path):
    specs = tuple(CandidateSpec(epoch, epoch * 76, 0.4 if epoch == 5 else 0.5, 0.2) for epoch in (5, 10, 15, 20, 25, 30))
    case = make_published_case(tmp_path, specs)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "STOPPING_SUMMARY_MISMATCH"


def test_selector_evidence_corruption_is_rejected(tmp_path):
    specs = (CandidateSpec(5, 380, 0.5, 0.2), CandidateSpec(10, 760, 0.4, 0.3))
    case = make_published_case(tmp_path, specs, corrupt_selector_index=1)
    result = finalize_run_bundle(case.bundle_path, case.fixture.locator_roots)
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "SELECTOR_REPLAY_MISMATCH"


@pytest.mark.parametrize("terminal", ["interrupted", "training_failed"])
def test_scientifically_incomplete_bundle_is_rejected(tmp_path, terminal):
    fixture, bundle = _simple(tmp_path, terminal)
    result = finalize_run_bundle(bundle, fixture.locator_roots)
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "SCIENTIFICALLY_INCOMPLETE"


def test_complete_finalization_failed_bundle_can_finalize_without_training(tmp_path):
    fixture, bundle = _simple(tmp_path, "finalization_failed")
    result = finalize_run_bundle(bundle, fixture.locator_roots)
    assert result["status"] == "SUCCEEDED"
    assert result["scientific_state"] == "COMPLETE"
    assert result["selected_checkpoint"]["completed_epoch"] == 10


def test_selection_contract_hash_mismatch_is_stable_failure(tmp_path):
    fixture, bundle = _simple(tmp_path)
    result = finalize_run_bundle(bundle, fixture.locator_roots, selection_contract_hash="f" * 64)
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "SELECTION_CONTRACT_MISMATCH"


def test_missing_bundle_is_stable_failure(tmp_path):
    result = finalize_run_bundle(tmp_path / "missing", {})
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "BUNDLE_NOT_FOUND"


def test_same_inputs_are_byte_and_identity_deterministic(tmp_path):
    fixture, bundle = _simple(tmp_path)
    first = finalize_run_bundle(bundle, fixture.locator_roots)
    second = finalize_run_bundle(bundle, fixture.locator_roots)
    assert first == second
    assert first["finalization_id"] == second["finalization_id"]
    assert first["finalization_result_hash"] == second["finalization_result_hash"]


def test_different_physical_roots_have_identical_finalization(tmp_path):
    left = make_published_case(tmp_path / "left", (CandidateSpec(5, 380, 0.5, 0.2), CandidateSpec(10, 760, 0.4, 0.3)))
    right = make_published_case(tmp_path / "right", (CandidateSpec(5, 380, 0.5, 0.2), CandidateSpec(10, 760, 0.4, 0.3)))
    assert finalize_run_bundle(left.bundle_path, left.fixture.locator_roots) == finalize_run_bundle(right.bundle_path, right.fixture.locator_roots)


def test_relocated_external_root_does_not_change_finalization(tmp_path):
    fixture, bundle = _simple(tmp_path)
    first = finalize_run_bundle(bundle, fixture.locator_roots)
    relocated = tmp_path / "relocated"
    shutil.copytree(fixture.external_root, relocated)
    second = finalize_run_bundle(bundle, {next(iter(fixture.locator_roots)): relocated})
    assert first == second


def test_finalizer_version_is_identity_bound(tmp_path):
    fixture, bundle = _simple(tmp_path)
    first = finalize_run_bundle(bundle, fixture.locator_roots)
    second = finalize_run_bundle(bundle, fixture.locator_roots, finalizer_version="p9-v2-finalizer-v2-test")
    assert first["status"] == second["status"] == "SUCCEEDED"
    assert first["finalization_id"] != second["finalization_id"]


def test_result_validation_does_not_rerun_selector(tmp_path):
    fixture, bundle = _simple(tmp_path)
    result = finalize_run_bundle(bundle, fixture.locator_roots)
    assert validate_finalization_result(result, bundle, fixture.locator_roots) == (True, None)
    changed = copy.deepcopy(result)
    changed["selected_checkpoint"]["optimizer_update"] += 1
    assert validate_finalization_result(changed, bundle, fixture.locator_roots)[0] is False


def test_resealed_wrong_finalizer_implementation_binding_is_rejected(tmp_path):
    fixture, bundle = _simple(tmp_path)
    result = finalize_run_bundle(bundle, fixture.locator_roots)
    result["finalizer_implementation_hash"] = "f" * 64
    preimage = {key: value for key, value in result.items() if key not in {"finalization_id", "finalization_result_hash"}}
    result_hash = canonical_sha256(preimage)
    result["finalization_result_hash"] = result_hash
    result["finalization_id"] = f"p9fin_{result_hash[:24]}"
    assert validate_finalization_result(result, bundle, fixture.locator_roots) == (False, "FINALIZER_IMPLEMENTATION_MISMATCH")


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda result: result.__setitem__("candidate_set_hash", "f" * 64), "CANDIDATE_SET_MISMATCH"),
        (lambda result: result["stopping_summary"].__setitem__("optimizer_update", 1), "STOPPING_SUMMARY_MISMATCH"),
        (lambda result: result["provenance"].__setitem__("source_inventory_digest", "f" * 64), "SOURCE_PROVENANCE_MISMATCH"),
    ],
)
def test_resealed_result_bundle_bindings_are_rejected(tmp_path, mutate, expected):
    fixture, bundle = _simple(tmp_path)
    result = finalize_run_bundle(bundle, fixture.locator_roots)
    mutate(result)
    preimage = {key: value for key, value in result.items() if key not in {"finalization_id", "finalization_result_hash"}}
    result_hash = canonical_sha256(preimage)
    result["finalization_result_hash"] = result_hash
    result["finalization_id"] = f"p9fin_{result_hash[:24]}"
    assert validate_finalization_result(result, bundle, fixture.locator_roots) == (False, expected)


def test_selection_and_result_schemas_accept_valid_reject_invalid(tmp_path):
    validate_instance("selection_contract", make_selection_contract())
    invalid = make_selection_contract()
    invalid["content"]["primary_metric"] = "MRR"
    with pytest.raises(P9V2SchemaError):
        validate_instance("selection_contract", invalid)
    fixture, bundle = _simple(tmp_path)
    result = finalize_run_bundle(bundle, fixture.locator_roots)
    validate_instance("finalization_result", result)
    result["evaluation_consumption_count"] = 1
    with pytest.raises(P9V2SchemaError):
        validate_instance("finalization_result", result)


def test_finalizer_import_boundary_has_no_training_stack():
    code = (
        "import sys; sys.path.insert(0, 'python'); import p9_v2_finalization; "
        "assert not any(name == 'torch' or name.startswith('torch.') for name in sys.modules); "
        "assert not any(name.startswith('p9_train') for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)
