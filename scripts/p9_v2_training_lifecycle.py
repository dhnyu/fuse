#!/usr/bin/env python3
"""Coarse native P9 v2 bundle/finalization/acceptance/resolver adapters."""

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

from p9_v2_acceptance import publish_acceptance, validate_acceptance  # noqa: E402
from p9_v2_canonical import canonical_json_bytes  # noqa: E402
from p9_v2_downstream import (  # noqa: E402
    AcceptedCheckpointResolver, load_acceptance_eligibility, make_acceptance_eligibility,
    publish_acceptance_eligibility,
)
from p9_v2_finalization import finalize_run_bundle, make_selection_contract, validate_finalization_result  # noqa: E402
from p9_v2_training_lifecycle import build_publish_native_bundle  # noqa: E402


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


def command_bundle(args: argparse.Namespace) -> dict:
    execution, authority = load(args.execution), load(args.authority)
    contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
    sources = [
        args.authority, args.contract, contract["roots"]["p8_bundle"] + "/hyperparameter_configuration_matrix.json",
        contract["roots"]["production_cache_acceptance"], "config/p7_deterministic_training.yml",
        "config/p6_model_dataloader.yml", "python/p9_v2_training_worker.py",
        "python/p9_v2_training_controller.py", "python/p9_v2_training_lifecycle.py",
    ]
    bundle, roots = build_publish_native_bundle(
        authority, execution["ledger_root"], execution["checkpoint_root"], sources[2], sources[3],
        contract["roots"]["canonical_publication"], sources)
    namespace, checkpoint_root = next(iter(roots.items()))
    return {"schema_version": "2.0.0", "artifact_type": "p9_v2_native_bundle_handoff",
            "bundle_id": bundle.bundle_id, "bundle_path": str(bundle.path),
            "checkpoint_namespace": namespace, "checkpoint_root": str(checkpoint_root)}


def command_finalize(args: argparse.Namespace) -> dict:
    bundle = load(args.bundle_record); roots = locator_roots(bundle)
    result = finalize_run_bundle(bundle["bundle_path"], roots,
                                 selection_contract_hash=make_selection_contract()["content_sha256"])
    valid, reason = validate_finalization_result(result, bundle["bundle_path"], roots)
    if not valid: raise RuntimeError(f"FINALIZATION_INVALID: {reason}")
    root = Path(args.publication_root) / "finalizations" / result["finalization_id"]
    result_path = publish_record(root / "finalization_result.json", result)
    return {**bundle, "schema_version": "2.0.0", "artifact_type": "p9_v2_native_finalization_handoff",
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
    return {**handoff, "schema_version": "2.0.0", "artifact_type": "p9_v2_native_acceptance_handoff",
            "acceptance_id": publication.acceptance_id, "acceptance_path": str(publication.path)}


def command_eligibility(args: argparse.Namespace) -> dict:
    handoff, authority = load(args.acceptance_record), load(args.authority)
    existing = load_acceptance_eligibility(args.existing_eligibility)
    entries = [entry for entry in existing["entries"] if entry["acceptance_id"] != handoff["acceptance_id"]]
    entries.append({"acceptance_id": handoff["acceptance_id"], "eligibility": "ELIGIBLE",
                    "authority_id": authority["identity"], "authority_hash": authority["content_sha256"]})
    value = make_acceptance_eligibility(entries, namespace=args.namespace)
    path = publish_acceptance_eligibility(value, Path(args.publication_root) / "eligibility")
    return {**handoff, "schema_version": "2.0.0", "artifact_type": "p9_v2_native_eligibility_handoff",
            "eligibility_id": value["eligibility_id"], "eligibility_path": str(path)}


def command_resolve(args: argparse.Namespace) -> dict:
    handoff = load(args.eligibility_record); roots = locator_roots(handoff)
    resolver = AcceptedCheckpointResolver(
        Path(args.publication_root) / "acceptances", Path(args.publication_root) / "bundles", roots,
        load_acceptance_eligibility(handoff["eligibility_path"]))
    resolved = resolver.resolve_accepted_checkpoint(handoff["acceptance_id"])
    return {"schema_version": "2.0.0", "artifact_type": "p9_v2_native_resolution_handoff",
            "acceptance_id": resolved.acceptance_id, "checkpoint_id": resolved.checkpoint_id,
            "payload_sha256": resolved.payload_sha256, "manifest_sha256": resolved.manifest_sha256,
            "completed_epoch": resolved.completed_epoch, "optimizer_update": resolved.optimizer_update,
            "evaluation_consumption_count": 0}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("bundle", "finalize", "accept", "eligibility", "resolve"))
    parser.add_argument("--result", required=True); parser.add_argument("--publication-root", default="")
    parser.add_argument("--execution"); parser.add_argument("--authority"); parser.add_argument("--contract")
    parser.add_argument("--bundle-record"); parser.add_argument("--finalization-record")
    parser.add_argument("--acceptance-record"); parser.add_argument("--eligibility-record")
    parser.add_argument("--existing-eligibility"); parser.add_argument("--namespace", default="p9-v2-canonical-native")
    args = parser.parse_args()
    function = {"bundle": command_bundle, "finalize": command_finalize, "accept": command_accept,
                "eligibility": command_eligibility, "resolve": command_resolve}[args.mode]
    value = function(args); path = publish_record(args.result, value)
    print(json.dumps({"status": "PASS", "result": str(path)}, sort_keys=True))


if __name__ == "__main__": main()
