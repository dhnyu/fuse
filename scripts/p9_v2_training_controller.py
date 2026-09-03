#!/usr/bin/env python3
"""Authority-gated P9 v2 controller and single canonical ledger writer."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
import os
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_line, parse_canonical_json  # noqa: E402
from p9_v2_ledger import read_ledger  # noqa: E402
from p9_v2_training_controller import (  # noqa: E402
    StartupInputs, TrainingController, TrainingControllerError, TrainingRunLock,
    accepted_scientific_configurations, validate_startup, validate_training_authority,
    latest_checkpoint_boundary, validate_worker_message, worker_response,
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def visible_gpu_count() -> int:
    output = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], text=True)
    return len([line for line in output.splitlines() if line.strip()])


def startup_inputs(contract: dict) -> StartupInputs:
    p8 = Path(contract["roots"]["p8_bundle"])
    configuration_matrix = Path(
        contract["roots"].get("configuration_matrix", p8 / "hyperparameter_configuration_matrix.json")
    )
    parents = dict(contract["parents"])
    parents["methodology_commit"] = contract["source"]["dissertation_commit"]
    return StartupInputs(
        fuse_root=ROOT, dissertation_root=Path.home() / "dhnyu-masters-dissertation",
        retirement_manifest=Path(contract["roots"]["immutable_publication"]) / "canonical/retirement" /
            contract["parents"]["v1_retirement_id"] / "retirement_manifest.json",
        p8_acceptance=p8 / "formal_experiment_plan_acceptance.json",
        p8_matrix=configuration_matrix,
        production_cache_root=Path(contract["roots"]["production_cache"]),
        production_cache_acceptance=Path(contract["roots"]["production_cache_acceptance"]),
        writable_root=Path(contract["roots"]["writable_runs"]),
        immutable_root=Path(contract["roots"]["immutable_publication"]),
        expected_dissertation_commit=contract["source"]["dissertation_commit"],
        expected_retirement_id=contract["parents"]["v1_retirement_id"],
        expected_p8_acceptance_id=contract["parents"]["p8_acceptance_id"],
        expected_cache_id=contract["parents"]["production_cache_id"],
        expected_cache_acceptance_id=contract["parents"]["production_cache_acceptance_id"],
        expected_cache_manifest_sha256=contract["production_cache_manifest_sha256"],
        expected_parents={key: parents[key] for key in (
            "methodology_commit", "p8_acceptance_id", "p7_runtime_acceptance_id", "p7_acceptance_id",
            "p6_acceptance_id", "p5_validation_acceptance_id", "p4_bank_id", "p4_bank_acceptance_id",
            "p3_cache_acceptance_id", "production_cache_id", "production_cache_acceptance_id", "v1_retirement_id")}
            | ({"selected_fm_acceptance_id": parents["selected_fm_acceptance_id"]}
               if "selected_fm_acceptance_id" in parents else {})
            | ({"full_model_acceptance_id": parents["full_model_acceptance_id"]}
               if "full_model_acceptance_id" in parents else {}),
    )


def run(args: argparse.Namespace) -> dict:
    authority = load(args.authority); validate_training_authority(authority)
    content = authority["content"]
    contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
    if args.noncanonical_pilot:
        output_root = Path(args.output).resolve()
        temporary_root = Path(tempfile.gettempdir()).resolve()
        if temporary_root not in output_root.parents or "--mode bounded-pilot" not in args.science_worker_command:
            raise TrainingControllerError("NONCANONICAL_PILOT_SCOPE_INVALID")
    else:
        accepted_ids, accepted_hashes = accepted_scientific_configurations(
            Path(contract["roots"]["immutable_publication"]) / "canonical", contract["roots"]["eligibility_snapshot"])
        validate_startup(authority, startup_inputs(contract), accepted_hashes=accepted_hashes,
                         accepted_configuration_ids=accepted_ids, cuda_devices=visible_gpu_count())
    run_root = Path(args.output) / content["scientific_run_key"]
    lock_root = run_root.parent / ".pilot-locks" if args.noncanonical_pilot else Path(contract["roots"]["execution_locks"])
    with TrainingRunLock(lock_root, content["scientific_run_key"]):
        controller = TrainingController(authority, run_root / "ledger", created_at=now())
        if controller.replay().last_committed_sequence == 0:
            controller.append("RUN_AUTHORIZED", {
                "authority_hash": authority["content_sha256"],
                "scientific_configuration_hash": content["scientific"]["configuration_hash"],
                "parent_identities": content["parents"], "duplicate_run_key": content["scientific_run_key"],
            }, occurred_at=now())
        state = controller.replay()
        if state.operational_state == "RUNNING":
            events = read_ledger(controller.ledger_root).events
            latest = next((event for event in reversed(events)
                           if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"), None)
            boundary = latest_checkpoint_boundary(events) or {
                "completed_epoch": 0, "resume_epoch": 1, "optimizer_update": 0}
            controller.append("TRAINING_INTERRUPTED", {
                "last_durable_boundary": boundary,
                "resumable_checkpoint_committed": latest is not None,
                "resume_policy": "EXACT_RESUME" if latest is not None else "RESTART",
                "interruption_reason": "CONTROLLER_RESTART_RECONCILIATION",
            }, occurred_at=now())
            state = controller.replay()
        if state.operational_state == "INTERRUPTED_RESUMABLE" and not controller.resume_allowed():
            raise TrainingControllerError("EXACT_RESUME_EVIDENCE_REQUIRED")
        if state.operational_state not in {"AUTHORIZED", "INTERRUPTED_RESUMABLE"}:
            raise TrainingControllerError("RUN_NOT_STARTABLE_FROM_REPLAY_STATE")
        controller.append("RUN_STARTING", {
            "owner_id": "p9-v2-controller", "execution_environment_digest": authority["content_sha256"],
            "training_lock_key": content["scientific_run_key"],
        }, occurred_at=now())
        command = shlex.split(args.science_worker_command)
        staging_root = run_root / "staging"; checkpoint_root = run_root / "checkpoints"
        staging_root.mkdir(parents=True, exist_ok=True); checkpoint_root.mkdir(parents=True, exist_ok=True)
        latest = next((event for event in reversed(read_ledger(controller.ledger_root).events)
                       if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"), None)
        environment = os.environ.copy()
        environment.update({
            "P9_V2_RUN_ID": controller.run_id,
            "P9_V2_STAGING_ROOT": str(staging_root),
            "P9_V2_CHECKPOINT_ROOT": str(checkpoint_root),
            "P9_V2_RESUME_CHECKPOINT": "" if latest is None else
                str(checkpoint_root / latest["payload"]["checkpoint_id"] / "checkpoint.pt"),
            "P9_V2_RESUME_CHECKPOINT_ID": "" if latest is None else latest["payload"]["checkpoint_id"],
        })
        stderr_path = run_root / "science_worker.stderr.log"
        stderr_stream = stderr_path.open("ab")
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=stderr_stream, env=environment)
        controller.append("RUN_STARTED", {"process_id": str(process.pid), "world_size": 2,
                                           "runtime_digest": authority["content_sha256"]}, occurred_at=now())
        assert process.stdout is not None and process.stdin is not None
        for raw in process.stdout:
            request = None
            try:
                request = parse_canonical_json(raw, json_line=True)
                validate_worker_message(request)
                response = controller.handle_worker_request(
                    request, staging_root=staging_root, checkpoint_root=checkpoint_root)
            except Exception as error:
                request_id = request.get("request_id", "p9req_" + "0" * 24) if isinstance(request, dict) else "p9req_" + "0" * 24
                response = worker_response(request_id, status="REJECTED",
                                           error_code=type(error).__name__, message=str(error)[:512])
            process.stdin.write(canonical_json_line(response)); process.stdin.flush()
            if response["message_type"] == "NACK": process.kill(); break
        process.stdin.close(); code = process.wait(); stderr_stream.close()
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        state = controller.replay()
        if code != 0:
            if state.operational_state == "TRAINING_FAILED":
                controller.close()
                raise TrainingControllerError(f"SCIENCE_WORKER_TRAINING_FAILED: {stderr[-1000:]}")
            events = read_ledger(controller.ledger_root).events
            boundary = latest_checkpoint_boundary(events)
            exact = boundary is not None
            if boundary is None: boundary = {"completed_epoch": 0, "resume_epoch": 1, "optimizer_update": 0}
            controller.append("TRAINING_INTERRUPTED", {
                "last_durable_boundary": {key: boundary[key] for key in ("completed_epoch", "resume_epoch", "optimizer_update")},
                "resumable_checkpoint_committed": exact, "resume_policy": "EXACT_RESUME" if exact else "RESTART",
                "interruption_reason": f"SCIENCE_WORKER_EXIT_{code}",
            }, occurred_at=now())
            raise TrainingControllerError(f"SCIENCE_WORKER_INTERRUPTED: {stderr[-1000:]}")
        if controller.replay().scientific_state != "COMPLETE":
            raise TrainingControllerError("SCIENCE_WORKER_EXITED_WITHOUT_TRAINING_COMPLETED")
        manifest = controller.close()
        result = {"schema_version": "2.0.0", "artifact_type": "p9_v2_training_execution",
                  "status": "COMPLETE", "run_id": controller.run_id,
                  "authority_id": authority["identity"], "authority_hash": authority["content_sha256"],
                  "scientific_run_key": content["scientific_run_key"],
                  "ledger_root": str(controller.ledger_root), "ledger_manifest": str(manifest),
                  "checkpoint_root": str(checkpoint_root), "evaluation_consumption_count": 0}
        result_path = run_root / "training_execution.json"
        result_path.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        result["training_execution"] = str(result_path)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("validate", "preflight", "run"))
    parser.add_argument("--authority", required=True); parser.add_argument("--contract", required=True)
    parser.add_argument("--output", default=""); parser.add_argument("--science-worker-command", default="")
    parser.add_argument("--noncanonical-pilot", action="store_true")
    args = parser.parse_args()
    if args.mode == "validate":
        authority = load(args.authority); validate_training_authority(authority)
        print(json.dumps({"status": "PASS", "authority_id": authority["identity"]}, sort_keys=True))
    elif args.mode == "preflight":
        authority = load(args.authority); contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
        accepted_ids, accepted_hashes = accepted_scientific_configurations(
            Path(contract["roots"]["immutable_publication"]) / "canonical", contract["roots"]["eligibility_snapshot"])
        result = validate_startup(authority, startup_inputs(contract), accepted_hashes=accepted_hashes,
                                  accepted_configuration_ids=accepted_ids, cuda_devices=visible_gpu_count())
        print(json.dumps({"status": "PASS", "authority_id": authority["identity"], **result}, sort_keys=True))
    else:
        if not args.output or not args.science_worker_command: parser.error("run requires output and science worker command")
        print(json.dumps(run(args), sort_keys=True))


if __name__ == "__main__": main()
