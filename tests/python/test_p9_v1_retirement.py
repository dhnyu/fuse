from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_recovery_transaction import (  # noqa: E402
    RecoveryTransactionController,
    TransactionContext,
    resolve_committed,
)
from p9_v1_retirement import (  # noqa: E402
    CANONICAL_ACCEPTANCE_ID,
    CANONICAL_CHECKPOINT_ID,
    FORMAL_AUTHORITY_IDS,
    HISTORICAL_STORE_NAMES,
    RECOVERY_AUTHORITY_IDS,
    RETIREMENT_ERROR_CODE,
    P9V1RetiredError,
    build_retirement_manifest,
    inspect_retirement_sources,
    publish_retirement_manifest,
)
from p9_v2_downstream import (  # noqa: E402
    AcceptedCheckpointResolver,
    CONSUMERS,
    load_acceptance_eligibility,
    resolve_consumer_checkpoint,
)
from p9_v2_legacy_import import inspect_legacy_run, validate_legacy_import  # noqa: E402
from p9_v2_schema import validate_instance  # noqa: E402


RETIRED_CLIS = (
    "scripts/p9_bounded_main_pilot.py",
    "scripts/p9_checkpoint_recovery_authorization.py",
    "scripts/p9_formal_authorization.py",
    "scripts/p9_formal_isolated_authorization.py",
    "scripts/p9_formal_reauthorization.py",
    "scripts/p9_formal_training.py",
    "scripts/p9_infrastructure.py",
    "scripts/p9_production_cache.py",
)


@pytest.fixture(scope="module")
def retirement_manifest():
    return build_retirement_manifest(ROOT)


@pytest.fixture(scope="module")
def historical_inspection():
    return inspect_legacy_run()


@pytest.mark.parametrize("relative", RETIRED_CLIS)
def test_all_v1_cli_entry_points_fail_closed_before_argument_parsing(relative):
    result = subprocess.run(
        [sys.executable, "-B", str(ROOT / relative), "--help"],
        cwd=ROOT, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 78
    assert RETIREMENT_ERROR_CODE in result.stderr
    assert "historical/read-only" in result.stderr
    assert "resolve_accepted_checkpoint" in result.stderr


def test_legacy_recovery_resolver_is_retired_without_fallback(tmp_path):
    with pytest.raises(P9V1RetiredError, match=RETIREMENT_ERROR_CODE):
        resolve_committed(tmp_path / "latest")


def test_legacy_recovery_controller_is_retired_before_state_or_lock_creation(tmp_path):
    context = TransactionContext(
        authority={}, reservation={}, operation={}, contract={},
        duplicate_operation_key="0" * 64, source_inventory_digest="1" * 64,
        lock_root=tmp_path / "locks", output_root=tmp_path / "output",
        store="retired", launch_commit="test", synthetic=True,
    )
    with pytest.raises(P9V1RetiredError, match=RETIREMENT_ERROR_CODE):
        RecoveryTransactionController(context)
    assert not (tmp_path / "locks").exists()
    assert not (tmp_path / "output").exists()


def test_retirement_manifest_records_all_authorities_stores_and_interfaces(retirement_manifest):
    value = retirement_manifest
    validate_instance("v1_retirement_manifest", value)
    assert [item["identity"] for item in value["formal_authorities"]] == list(FORMAL_AUTHORITY_IDS)
    assert [item["identity"] for item in value["recovery_authorities"]] == list(RECOVERY_AUTHORITY_IDS)
    assert [item["name"] for item in value["historical_stores"]] == list(HISTORICAL_STORE_NAMES)
    assert len(value["formal_authorities"]) == 9
    assert len(value["recovery_authorities"]) == 3
    assert len(value["historical_stores"]) == 6
    assert all(item["status"] == "RETIRED_INELIGIBLE" for item in [*value["formal_authorities"], *value["recovery_authorities"]])
    assert all(item["status"] == "HISTORICAL_READ_ONLY" for item in value["historical_stores"])
    assert value["replacement"] == {
        "acceptance_id": CANONICAL_ACCEPTANCE_ID,
        "checkpoint_id": CANONICAL_CHECKPOINT_ID,
        "resolver_contract": "resolve_accepted_checkpoint(acceptance_identity)",
    }
    assert value == build_retirement_manifest(ROOT)


def test_retirement_manifest_publication_is_idempotent_and_collision_safe(retirement_manifest, tmp_path):
    first = publish_retirement_manifest(retirement_manifest, tmp_path)
    before = first.read_bytes()
    second = publish_retirement_manifest(retirement_manifest, tmp_path)
    assert first == second and second.read_bytes() == before
    corrupt = copy.deepcopy(retirement_manifest)
    corrupt["status"] = "V1_RETIRED_READ_ONLY"
    first.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="collision"):
        publish_retirement_manifest(corrupt, tmp_path)


def test_read_only_historical_inspection_remains_complete(historical_inspection):
    validation = validate_legacy_import(historical_inspection)
    assert validation.valid and validation.pair_count == 25 and validation.missing_blocking == 0
    assert historical_inspection.source_inventory_digest == "282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c"
    assert historical_inspection.terminal_state["state"] == "FAILED_NONRESUMABLE"


def test_source_inventory_is_read_only_and_repeatable(retirement_manifest):
    first = inspect_retirement_sources(ROOT)
    second = inspect_retirement_sources(ROOT)
    assert first == second
    assert first["formal_authorities"] == retirement_manifest["formal_authorities"]
    assert first["recovery_authorities"] == retirement_manifest["recovery_authorities"]
    assert first["historical_stores"] == retirement_manifest["historical_stores"]


def test_active_target_graphs_expose_only_retirement_guards():
    expression = r'''
for (script in c("_targets.R", "_targets_p9_formal.R", "_targets_p9_recovery.R")) {
  manifest <- targets::tar_manifest(script = script)
  p9 <- manifest$name[grepl("^p9", manifest$name)]
  expected <- switch(script,
    "_targets.R" = "p9_v1_main_execution_retired",
    "_targets_p9_formal.R" = "p9_v1_formal_execution_retired",
    "_targets_p9_recovery.R" = "p9_v1_recovery_execution_retired")
  if (!identical(p9, expected)) stop(paste(script, paste(p9, collapse = ",")))
}
'''
    result = subprocess.run(["Rscript", "-e", expression], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_canonical_v2_chain_and_all_consumers_remain_identical(historical_inspection):
    root = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical")
    eligibility = load_acceptance_eligibility(next((root / "eligibility").glob("p9elig_*.json")))
    resolver = AcceptedCheckpointResolver(
        root / "acceptances", root / "bundles",
        {"p9-v1-history": historical_inspection.sources.attempt_root}, eligibility,
    )
    resolved = resolver.resolve_accepted_checkpoint(CANONICAL_ACCEPTANCE_ID)
    values = [resolve_consumer_checkpoint(name, CANONICAL_ACCEPTANCE_ID, resolver) for name in CONSUMERS]
    assert resolved.checkpoint_id == CANONICAL_CHECKPOINT_ID
    assert len(values) == 5 and all(value == resolved for value in values)


@pytest.mark.parametrize("consumer", CONSUMERS)
@pytest.mark.parametrize(
    "identity",
    [
        "p9ck_42f7957d2ea998ac9e8ff705",
        "p9a_9d6f0554553ac43371b47efd",
        "p9ra_2b5e0dc9eebb81c028fefedf",
        "/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal",
        "/tmp/manual-checkpoint.pt",
        "latest",
        "/tmp/p9rb_78322173dfd691baf67a44a0",
        "/tmp/p9fin_2383ccda2e5391ecf75c6010",
    ],
)
def test_all_consumers_reject_every_v1_manual_and_direct_form(
    historical_inspection, consumer, identity
):
    root = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical")
    eligibility = load_acceptance_eligibility(next((root / "eligibility").glob("p9elig_*.json")))
    resolver = AcceptedCheckpointResolver(
        root / "acceptances", root / "bundles",
        {"p9-v1-history": historical_inspection.sources.attempt_root}, eligibility,
    )
    with pytest.raises(Exception, match="INVALID_ACCEPTANCE_ID"):
        resolve_consumer_checkpoint(consumer, identity, resolver)
