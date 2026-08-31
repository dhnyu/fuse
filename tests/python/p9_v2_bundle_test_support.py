from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import (  # noqa: E402
    COMMIT_PATH,
    INVENTORY_PATH,
    RunBundleInputs,
    make_bound_document,
    make_filesystem_locator,
)
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_bytes  # noqa: E402
from p9_v2_finalization import make_selection_contract, selection_contract_content  # noqa: E402
from p9_v2_test_support import (  # noqa: E402
    HASH_A,
    HASH_B,
    HASH_C,
    RUN_ID,
    append_event,
    initialized_writer,
    payload,
)


CHECKPOINT_IDS = ("p9ck_" + "b" * 24, "p9ck_" + "e" * 24)
VALIDATION_IDS = ("p9val_" + "c" * 24, "p9val_" + "d" * 24)
NAMESPACE = "synthetic-checkpoints"


@dataclass(frozen=True)
class BundleFixture:
    ledger_root: Path
    external_root: Path
    locator_roots: dict[str, Path]
    inputs: RunBundleInputs
    external_paths: tuple[Path, ...]


def _documents(config_variant: str = "base", selection_variant: str = "base") -> dict[str, dict[str, Any]]:
    configuration = make_bound_document(
        "p9cfg_" + "1" * 24,
        {"configuration": "synthetic", "variant": config_variant, "updates_per_epoch": 76},
    )
    runtime = make_bound_document(
        "p9runtime_" + "2" * 24,
        {"python": "3.14", "torch": "synthetic", "world_size": 2},
    )
    parents = make_bound_document(
        "p9parents_" + "3" * 24,
        {
            "identities": {"p8_acceptance": "p8acc_synthetic"},
            "hashes": {"p8_acceptance": HASH_A},
        },
    )
    cache = make_bound_document(
        "p9ca_" + "4" * 24,
        {"cache_id": "p9cache_synthetic", "inventory_sha256": HASH_B},
    )
    sampler = make_bound_document(
        "p9sampler_" + "5" * 24,
        {"global_batch": 32, "per_rank_batch": 16, "world_size": 2, "uniqueness": "strict"},
    )
    if selection_variant == "base":
        selection = make_selection_contract()
    else:
        selection_content = selection_contract_content()
        selection_content["early_stopping_patience"] = 5
        selection_hash = canonical_sha256(selection_content)
        selection = make_bound_document(f"p9selc_{selection_hash[:24]}", selection_content)
    authority_content = {
        "run_id": RUN_ID,
        "scientific_configuration_id": configuration["identity"],
        "scientific_configuration_hash": configuration["content_sha256"],
        "source_parents_id": parents["identity"],
        "source_parents_hash": parents["content_sha256"],
        "cache_acceptance_id": cache["identity"],
        "cache_acceptance_hash": cache["content_sha256"],
        "sampler_contract_id": sampler["identity"],
        "sampler_contract_hash": sampler["content_sha256"],
        "selection_contract_id": selection["identity"],
        "selection_contract_hash": selection["content_sha256"],
    }
    authority = make_bound_document("p9authv2_" + "7" * 24, authority_content)
    return {
        "authority": authority,
        "scientific_configuration": configuration,
        "runtime": runtime,
        "source_parents": parents,
        "cache_acceptance": cache,
        "sampler_contract": sampler,
        "selection_contract": selection,
    }


def _write_checkpoint(
    external_root: Path,
    index: int,
    *,
    payload_variant: str,
) -> tuple[dict[str, dict[str, Any]], tuple[Path, Path]]:
    checkpoint_id = CHECKPOINT_IDS[index]
    relative_root = Path("objects") / checkpoint_id
    physical_root = external_root / relative_root
    physical_root.mkdir(parents=True, exist_ok=True)
    payload_path = physical_root / "checkpoint.pt"
    manifest_path = physical_root / "checkpoint_manifest.json"
    payload_path.write_bytes(f"synthetic-checkpoint-{index}-{payload_variant}".encode("ascii"))
    manifest_path.write_bytes(canonical_json_bytes({
        "checkpoint_id": checkpoint_id,
        "payload_sha256": sha256_bytes(payload_path.read_bytes()),
        "complete": True,
    }))
    manifest_hash = sha256_bytes(manifest_path.read_bytes())
    payload_locator = make_filesystem_locator(
        namespace=NAMESPACE,
        relative_path=(relative_root / "checkpoint.pt").as_posix(),
        physical_path=payload_path,
        role="checkpoint_payload",
        media_type="application/x-pytorch",
        associated_manifest_sha256=manifest_hash,
    )
    manifest_locator = make_filesystem_locator(
        namespace=NAMESPACE,
        relative_path=(relative_root / "checkpoint_manifest.json").as_posix(),
        physical_path=manifest_path,
        role="checkpoint_manifest",
        media_type="application/json",
    )
    return {"payload": payload_locator, "manifest": manifest_locator}, (payload_path, manifest_path)


def make_bundle_fixture(
    root: Path,
    *,
    terminal: str = "complete",
    config_variant: str = "base",
    selection_variant: str = "base",
    payload_variant: str = "base",
    reverse_inputs: bool = False,
    completion_update: int = 760,
) -> BundleFixture:
    root.mkdir(parents=True, exist_ok=True)
    documents = _documents(config_variant, selection_variant)
    external_root = root / "external"
    external_root.mkdir()
    locator_map: dict[str, dict[str, dict[str, Any]]] = {}
    external_paths: list[Path] = []
    if terminal != "training_failed":
        for index, checkpoint_id in enumerate(CHECKPOINT_IDS):
            pair, paths = _write_checkpoint(external_root, index, payload_variant=payload_variant)
            locator_map[checkpoint_id] = pair
            external_paths.extend(paths)
    ledger_root = root / "ledger"
    writer = initialized_writer(ledger_root)
    append_event(writer, "RUN_AUTHORIZED", payload(
        "RUN_AUTHORIZED",
        authority_hash=documents["authority"]["content_sha256"],
        scientific_configuration_hash=documents["scientific_configuration"]["content_sha256"],
        parent_identities=documents["source_parents"]["content"]["identities"],
    ))
    append_event(writer, "RUN_STARTING")
    append_event(writer, "RUN_STARTED", payload(
        "RUN_STARTED", runtime_digest=documents["runtime"]["content_sha256"]
    ))
    if terminal == "training_failed":
        append_event(writer, "UPDATE_COMMITTED")
        append_event(writer, "TRAINING_FAILED")
    else:
        previous_update = 0
        for index, (epoch, update) in enumerate(((5, 380), (10, 760))):
            checkpoint_id = CHECKPOINT_IDS[index]
            validation_id = VALIDATION_IDS[index]
            pair = locator_map[checkpoint_id]
            append_event(writer, "EPOCH_STARTED", payload(
                "EPOCH_STARTED", epoch=previous_update // 76 + 1,
                starting_optimizer_update=previous_update,
            ))
            append_event(writer, "PROGRESS_SUMMARY_COMMITTED", payload(
                "PROGRESS_SUMMARY_COMMITTED",
                first_update=previous_update + 1,
                last_update=update,
                ending_epoch=epoch,
            ))
            append_event(writer, "VALIDATION_CHECKPOINT_COMMITTED", payload(
                "VALIDATION_CHECKPOINT_COMMITTED",
                completed_epoch=epoch,
                resume_epoch=epoch + 1,
                optimizer_update=update,
                validation_id=validation_id,
                checkpoint_id=checkpoint_id,
                checkpoint_payload_sha256=pair["payload"]["content_sha256"],
                checkpoint_manifest_sha256=pair["manifest"]["content_sha256"],
                validation_retrieval_loss=0.5 - index * 0.1,
                mean_source_separation_margin=0.2 + index * 0.05,
                selector_state={"best_checkpoint_id": checkpoint_id, "events_without_improvement": 0},
                sampler={"epoch": epoch + 1, "cursor": 0, "state_sha256": HASH_C},
            ))
            append_event(writer, "EARLY_STOPPING_UPDATED", payload(
                "EARLY_STOPPING_UPDATED", best_checkpoint_id=checkpoint_id,
                events_without_improvement=0,
            ))
            previous_update = update
        if terminal in {"complete", "finalization_failed"}:
            append_event(writer, "TRAINING_COMPLETED", payload(
                "TRAINING_COMPLETED", completed_epoch=10, resume_epoch=11,
                optimizer_update=completion_update,
            ))
            if terminal == "finalization_failed":
                append_event(writer, "FINALIZATION_STARTED")
                append_event(writer, "FINALIZATION_FAILED")
        elif terminal == "interrupted":
            append_event(writer, "TRAINING_INTERRUPTED", payload(
                "TRAINING_INTERRUPTED",
                last_durable_boundary={"completed_epoch": 10, "resume_epoch": 11, "optimizer_update": 760},
            ))
        else:
            raise ValueError(f"unknown terminal fixture: {terminal}")
    writer.close()
    source_entries = (
        {"logical_path": "python/model.py", "role": "scientific_source", "content_sha256": HASH_A},
        {"logical_path": "config/training.yml", "role": "scientific_configuration_source", "content_sha256": HASH_B},
    )
    if reverse_inputs:
        source_entries = tuple(reversed(source_entries))
        locator_map = dict(reversed(tuple(locator_map.items())))
    inputs = RunBundleInputs(
        authority=documents["authority"],
        scientific_configuration=documents["scientific_configuration"],
        runtime=documents["runtime"],
        source_parents=documents["source_parents"],
        cache_acceptance=documents["cache_acceptance"],
        sampler_contract=documents["sampler_contract"],
        selection_contract=documents["selection_contract"],
        source_inventory=source_entries,
        checkpoint_locators=locator_map,
    )
    return BundleFixture(
        ledger_root=ledger_root,
        external_root=external_root,
        locator_roots={NAMESPACE: external_root},
        inputs=inputs,
        external_paths=tuple(external_paths),
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reseal_bundle(root: Path, changed_internal_path: str | None = None) -> Path:
    """Test-only reseal so semantic corruptions survive structural hash checks."""

    inventory_path = root / INVENTORY_PATH
    inventory = read_json(inventory_path)
    if changed_internal_path is not None:
        raw = (root / changed_internal_path).read_bytes()
        entry = next(item for item in inventory["entries"] if item["path"] == changed_internal_path)
        entry["size_bytes"] = len(raw)
        entry["sha256"] = sha256_bytes(raw)
    inventory_bytes = canonical_json_bytes(inventory)
    inventory_path.write_bytes(inventory_bytes)
    manifest_path = root / COMMIT_PATH
    manifest = read_json(manifest_path)
    manifest["inventory"] = {
        "path": INVENTORY_PATH,
        "sha256": sha256_bytes(inventory_bytes),
        "size_bytes": len(inventory_bytes),
    }
    preimage = {key: value for key, value in manifest.items() if key not in {"bundle_id", "bundle_content_sha256"}}
    content_hash = canonical_sha256(preimage)
    manifest["bundle_content_sha256"] = content_hash
    manifest["bundle_id"] = f"p9rb_{content_hash[:24]}"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    destination = root.with_name(manifest["bundle_id"])
    if destination != root:
        root.rename(destination)
    return destination
