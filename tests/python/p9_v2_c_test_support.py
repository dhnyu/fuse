from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import (  # noqa: E402
    RunBundleInputs,
    build_run_bundle,
    make_filesystem_locator,
    publish_run_bundle,
)
from p9_v2_bundle_test_support import BundleFixture, NAMESPACE, _documents  # noqa: E402
from p9_v2_canonical import canonical_json_bytes, sha256_bytes  # noqa: E402
from p9_v2_finalization import (  # noqa: E402
    evaluate_selection_candidate,
    qualifies_patience_reset,
)
from p9_v2_test_support import HASH_C, append_event, initialized_writer, payload  # noqa: E402


@dataclass(frozen=True)
class CandidateSpec:
    epoch: int
    update: int
    loss: float
    margin: float


@dataclass(frozen=True)
class PublishedCase:
    fixture: BundleFixture
    bundle_path: Path
    bundle_store: Path
    candidate_specs: tuple[CandidateSpec, ...]


def _ids(index: int) -> tuple[str, str]:
    return f"p9ck_{index + 1:024x}", f"p9val_{index + 1001:024x}"


def _checkpoint(
    external_root: Path, index: int, checkpoint_id: str
) -> tuple[dict[str, dict[str, Any]], tuple[Path, Path]]:
    relative = Path("objects") / checkpoint_id
    root = external_root / relative
    root.mkdir(parents=True)
    payload_path = root / "checkpoint.pt"
    manifest_path = root / "checkpoint_manifest.json"
    payload_path.write_bytes(f"v2-c-synthetic-checkpoint-{index}".encode("ascii"))
    manifest_path.write_bytes(canonical_json_bytes({
        "checkpoint_id": checkpoint_id,
        "payload_sha256": sha256_bytes(payload_path.read_bytes()),
        "complete": True,
    }))
    manifest_hash = sha256_bytes(manifest_path.read_bytes())
    return {
        "payload": make_filesystem_locator(
            namespace=NAMESPACE,
            relative_path=(relative / payload_path.name).as_posix(),
            physical_path=payload_path,
            role="checkpoint_payload",
            media_type="application/x-pytorch",
            associated_manifest_sha256=manifest_hash,
        ),
        "manifest": make_filesystem_locator(
            namespace=NAMESPACE,
            relative_path=(relative / manifest_path.name).as_posix(),
            physical_path=manifest_path,
            role="checkpoint_manifest",
            media_type="application/json",
        ),
    }, (payload_path, manifest_path)


def _candidate(spec: CandidateSpec) -> dict[str, Any]:
    return {
        "completed_epoch": spec.epoch,
        "validation_retrieval_loss": spec.loss,
        "mean_source_separation_margin": spec.margin,
    }


def make_published_case(
    root: Path,
    specs: tuple[CandidateSpec, ...],
    *,
    terminal: str = "complete",
    corrupt_selector_index: int | None = None,
) -> PublishedCase:
    fixture_root = root / "fixture"
    fixture_root.mkdir(parents=True)
    documents = _documents()
    external_root = fixture_root / "external"
    external_root.mkdir()
    locators: dict[str, dict[str, dict[str, Any]]] = {}
    paths: list[Path] = []
    for index, _ in enumerate(specs):
        checkpoint_id, _ = _ids(index)
        pair, pair_paths = _checkpoint(external_root, index, checkpoint_id)
        locators[checkpoint_id] = pair
        paths.extend(pair_paths)
    ledger_root = fixture_root / "ledger"
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
    best_spec: CandidateSpec | None = None
    best_id: str | None = None
    non_improvements = 0
    previous_update = 0
    for index, spec in enumerate(specs):
        checkpoint_id, validation_id = _ids(index)
        candidate = _candidate(spec)
        previous_best = None if best_spec is None else _candidate(best_spec)
        selected, basis = evaluate_selection_candidate(candidate, previous_best, 0.0001)
        resets_patience = qualifies_patience_reset(candidate, previous_best, 0.0001)
        if selected:
            best_spec = spec
            best_id = checkpoint_id
        if resets_patience:
            non_improvements = 0
        else:
            non_improvements += 1
        stored_count = non_improvements + (1 if corrupt_selector_index == index else 0)
        append_event(writer, "EPOCH_STARTED", payload(
            "EPOCH_STARTED", epoch=1 if index == 0 else specs[index - 1].epoch + 1,
            starting_optimizer_update=previous_update,
        ))
        append_event(writer, "PROGRESS_SUMMARY_COMMITTED", payload(
            "PROGRESS_SUMMARY_COMMITTED", first_update=previous_update + 1,
            last_update=spec.update, ending_epoch=spec.epoch,
        ))
        pair = locators[checkpoint_id]
        append_event(writer, "VALIDATION_CHECKPOINT_COMMITTED", payload(
            "VALIDATION_CHECKPOINT_COMMITTED",
            completed_epoch=spec.epoch,
            resume_epoch=spec.epoch + 1,
            optimizer_update=spec.update,
            validation_id=validation_id,
            checkpoint_id=checkpoint_id,
            checkpoint_payload_sha256=pair["payload"]["content_sha256"],
            checkpoint_manifest_sha256=pair["manifest"]["content_sha256"],
            validation_retrieval_loss=spec.loss,
            mean_source_separation_margin=spec.margin,
            selector_state={"best_checkpoint_id": best_id, "events_without_improvement": stored_count},
            sampler={"epoch": spec.epoch + 1, "cursor": 0, "state_sha256": HASH_C},
        ))
        append_event(writer, "EARLY_STOPPING_UPDATED", payload(
            "EARLY_STOPPING_UPDATED", best_checkpoint_id=best_id,
            events_without_improvement=stored_count, decision_basis=basis,
        ))
        previous_update = spec.update
    if terminal in {"complete", "finalization_failed"}:
        final = specs[-1]
        append_event(writer, "TRAINING_COMPLETED", payload(
            "TRAINING_COMPLETED", completed_epoch=final.epoch,
            resume_epoch=final.epoch + 1, optimizer_update=final.update,
            reason="EARLY_STOPPING" if non_improvements == 4 else "MAXIMUM_TRAJECTORY",
        ))
        if terminal == "finalization_failed":
            append_event(writer, "FINALIZATION_STARTED")
            append_event(writer, "FINALIZATION_FAILED")
    elif terminal == "interrupted":
        final = specs[-1]
        append_event(writer, "TRAINING_INTERRUPTED", payload(
            "TRAINING_INTERRUPTED",
            last_durable_boundary={"completed_epoch": final.epoch, "resume_epoch": final.epoch + 1, "optimizer_update": final.update},
        ))
    else:
        raise ValueError(terminal)
    writer.close()
    inputs = RunBundleInputs(
        authority=documents["authority"],
        scientific_configuration=documents["scientific_configuration"],
        runtime=documents["runtime"],
        source_parents=documents["source_parents"],
        cache_acceptance=documents["cache_acceptance"],
        sampler_contract=documents["sampler_contract"],
        selection_contract=documents["selection_contract"],
        source_inventory=(
            {"logical_path": "config/training.yml", "role": "scientific_configuration_source", "content_sha256": "b" * 64},
            {"logical_path": "python/model.py", "role": "scientific_source", "content_sha256": "a" * 64},
        ),
        checkpoint_locators=locators,
    )
    fixture = BundleFixture(
        ledger_root=ledger_root,
        external_root=external_root,
        locator_roots={NAMESPACE: external_root},
        inputs=inputs,
        external_paths=tuple(paths),
    )
    candidate = build_run_bundle(ledger_root, inputs, fixture.locator_roots)
    store = root / "bundles"
    publication = publish_run_bundle(candidate, store, fixture.locator_roots)
    return PublishedCase(fixture, publication.path, store, specs)
