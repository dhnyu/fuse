#!/usr/bin/env python3
"""Coarse native current training bundle/finalization/acceptance/resolver adapters."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from training_acceptance import publish_acceptance, validate_acceptance  # noqa: E402
from artifact_protocol import canonical_json_bytes  # noqa: E402
from checkpoint_resolution import (  # noqa: E402
    AcceptedCheckpointResolver, load_acceptance_eligibility, make_acceptance_eligibility,
    publish_acceptance_eligibility,
)
import training_finalization as finalization_module  # noqa: E402
import training_lifecycle as lifecycle_module  # noqa: E402
from training_campaign import s08_selection_document  # noqa: E402
from training_finalization import finalize_run_bundle, make_selection_contract, validate_finalization_result  # noqa: E402
from training_lifecycle import build_publish_native_bundle  # noqa: E402


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def publish_record(path: str | Path, value: dict) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(value)
    if path.exists():
        if path.read_bytes() != raw: raise RuntimeError("LIFECYCLE_RECORD_COLLISION")
        return path
    temporary = path.with_name(f".{path.name}.incomplete-{os.getpid()}")
    with temporary.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    return path


def locator_roots(bundle_record: dict) -> dict[str, Path]:
    return {bundle_record["checkpoint_namespace"]: Path(bundle_record["checkpoint_root"])}


def configure_current_selection(matrix_path: str | Path) -> dict:
    global make_selection_contract
    selection = s08_selection_document(load(matrix_path))
    provider = lambda: selection
    make_selection_contract = provider
    finalization_module.make_selection_contract = provider
    lifecycle_module.make_selection_contract = provider
    return selection


def command_bundle(args: argparse.Namespace) -> dict:
    execution, authority = load(args.execution), load(args.authority)
    contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
    matrix = args.matrix or contract["roots"]["experiment_plan"]
    configure_current_selection(matrix)
    sources = [
        args.authority, args.contract, matrix,
        contract["roots"]["production_cache_acceptance"], "config/training.yml",
        "config/model_inputs.yml", "python/training_prepared_cache.py",
        "python/training_worker.py",
        "python/training_controller.py", "python/training_lifecycle.py",
        "python/training_configuration.py", "python/model_families.py",
    ]
    bundle, roots = build_publish_native_bundle(
        authority, execution["ledger_root"], execution["checkpoint_root"], sources[2], sources[3],
        contract["roots"]["canonical_publication"], sources)
    namespace, checkpoint_root = next(iter(roots.items()))
    return {"schema_version": "2.0.0", "artifact_type": "training_native_bundle_handoff",
            "bundle_id": bundle.bundle_id, "bundle_path": str(bundle.path),
            "checkpoint_namespace": namespace, "checkpoint_root": str(checkpoint_root),
            "matrix_path": str(Path(matrix).resolve())}


def command_finalize(args: argparse.Namespace) -> dict:
    bundle = load(args.bundle_record); roots = locator_roots(bundle)
    configure_current_selection(bundle["matrix_path"])
    result = finalize_run_bundle(bundle["bundle_path"], roots,
                                 selection_contract_hash=make_selection_contract()["content_sha256"])
    valid, reason = validate_finalization_result(result, bundle["bundle_path"], roots)
    if not valid: raise RuntimeError(f"FINALIZATION_INVALID: {reason}")
    root = Path(args.publication_root) / "finalizations" / result["finalization_id"]
    result_path = publish_record(root / "finalization_result.json", result)
    return {**bundle, "schema_version": "2.0.0", "artifact_type": "training_native_finalization_handoff",
            "finalization_id": result["finalization_id"], "finalization_path": str(result_path)}


def command_accept(args: argparse.Namespace) -> dict:
    handoff, authority = load(args.finalization_record), load(args.authority)
    roots = locator_roots(handoff); finalization = load(handoff["finalization_path"])
    publication = publish_acceptance(
        finalization, handoff["bundle_path"], roots, Path(args.publication_root) / "acceptances",
        authority_id=authority["identity"], authority_hash=authority["content_sha256"])
    valid = validate_acceptance(publication.acceptance_id, Path(args.publication_root) / "acceptances",
                                Path(args.publication_root) / "bundles", roots)
    if not valid.valid: raise RuntimeError(f"ACCEPTANCE_INVALID: {valid.error_code}")
    return {**handoff, "schema_version": "2.0.0", "artifact_type": "training_native_acceptance_handoff",
            "acceptance_id": publication.acceptance_id, "acceptance_path": str(publication.path)}


def command_eligibility(args: argparse.Namespace) -> dict:
    handoff, authority = load(args.acceptance_record), load(args.authority)
    existing = (load_acceptance_eligibility(args.existing_eligibility)
                if Path(args.existing_eligibility).is_file() else {"entries": []})
    entries = [entry for entry in existing["entries"] if entry["acceptance_id"] != handoff["acceptance_id"]]
    entries.append({"acceptance_id": handoff["acceptance_id"], "eligibility": "ELIGIBLE",
                    "authority_id": authority["identity"], "authority_hash": authority["content_sha256"]})
    value = make_acceptance_eligibility(entries, namespace=args.namespace)
    path = publish_acceptance_eligibility(value, Path(args.publication_root) / "eligibility")
    current = Path(args.existing_eligibility); current.parent.mkdir(parents=True, exist_ok=True)
    temporary = current.with_name(f".{current.name}.{os.getpid()}.tmp")
    temporary.write_bytes(canonical_json_bytes(value)); os.replace(temporary, current)
    return {**handoff, "schema_version": "2.0.0", "artifact_type": "training_native_eligibility_handoff",
            "eligibility_id": value["eligibility_id"], "eligibility_path": str(path)}


def command_resolve(args: argparse.Namespace) -> dict:
    handoff = load(args.eligibility_record); roots = locator_roots(handoff)
    resolver = AcceptedCheckpointResolver(
        Path(args.publication_root) / "acceptances", Path(args.publication_root) / "bundles", roots,
        load_acceptance_eligibility(handoff["eligibility_path"]))
    resolved = resolver.resolve_accepted_checkpoint(handoff["acceptance_id"])
    return {"schema_version": "2.0.0", "artifact_type": "training_native_resolution_handoff",
            "acceptance_id": resolved.acceptance_id, "checkpoint_id": resolved.checkpoint_id,
            "payload_sha256": resolved.payload_sha256, "manifest_sha256": resolved.manifest_sha256,
            "completed_epoch": resolved.completed_epoch, "optimizer_update": resolved.optimizer_update,
            "evaluation_consumption_count": 0}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("bundle", "finalize", "accept", "eligibility", "resolve"))
    parser.add_argument("--result", required=True); parser.add_argument("--publication-root", default="")
    parser.add_argument("--execution"); parser.add_argument("--authority"); parser.add_argument("--contract")
    parser.add_argument("--bundle-record"); parser.add_argument("--finalization-record"); parser.add_argument("--matrix")
    parser.add_argument("--acceptance-record"); parser.add_argument("--eligibility-record")
    parser.add_argument("--existing-eligibility"); parser.add_argument("--namespace", default="current-training")
    args = parser.parse_args()
    function = {"bundle": command_bundle, "finalize": command_finalize, "accept": command_accept,
                "eligibility": command_eligibility, "resolve": command_resolve}[args.mode]
    value = function(args); path = publish_record(args.result, value)
    print(json.dumps({"status": "PASS", "result": str(path)}, sort_keys=True))


if __name__ == "__main__": main()
