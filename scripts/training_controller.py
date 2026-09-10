#!/usr/bin/env python3
"""Authority-gated current training controller and single canonical ledger writer."""

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

from artifact_protocol import canonical_json_line, parse_canonical_json  # noqa: E402
from training_ledger import read_ledger  # noqa: E402
from training_controller import (  # noqa: E402
    StartupInputs, TrainingController, TrainingControllerError, TrainingRunLock,
    accepted_scientific_configurations, validate_startup, validate_training_authority,
    latest_checkpoint_boundary, training_run_id, validate_worker_message, worker_response,
)
from training_progress import RunProgress, configured_log_root, validation_progress  # noqa: E402
from training_transport import (  # noqa: E402
    gpu_pair_environment, launch_formal_worker_after_preflight, perform_locked_transport_preflight,
    require_no_conflicting_gpu_workload,
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def visible_gpu_count() -> int:
    output = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], text=True)
    return len([line for line in output.splitlines() if line.strip()])


def require_current_contract_ready(contract: dict) -> None:
    if contract.get("migration_status") != "READY":
        raise TrainingControllerError("CURRENT_METHODOLOGY_RECOMPUTATION_REQUIRED")


def progress_logger(authority: dict, contract: dict, *, require_existing: bool = False) -> RunProgress:
    scientific = authority["content"]["scientific"]
    phase = scientific["phase"]
    config_or_model = (scientific["configuration_id"] if phase == "OFAT"
                       else scientific["model_id"])
    execution = contract["execution"]
    return RunProgress(
        configured_log_root(ROOT, contract), phase=phase,
        config_or_model=config_or_model,
        authority_id=authority["identity"], run_id=training_run_id(authority),
        patience_limit=int(execution["early_stopping_patience_events"]),
        epoch_limit=int(execution["maximum_epochs"]),
        update_limit=int(execution["maximum_updates"]), create=True,
        require_existing=require_existing,
    )


def disposable_transport_preflight(args: argparse.Namespace) -> dict:
    """Exercise the exact locked formal transport gate without creating a run ledger."""
    authority = load(args.authority); validate_training_authority(authority)
    contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
    require_current_contract_ready(contract)
    log_root = Path(args.log_root).resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if temporary_root not in log_root.parents:
        raise TrainingControllerError("S09_TRANSPORT_PREFLIGHT_LOG_ROOT_MUST_BE_TEMPORARY")
    scientific = authority["content"]["scientific"]
    progress = RunProgress(
        log_root, phase=scientific["phase"],
        config_or_model=scientific.get("configuration_id", scientific.get("model_id")),
        authority_id=authority["identity"], run_id=training_run_id(authority),
        patience_limit=int(contract["execution"]["early_stopping_patience_events"]),
        epoch_limit=int(contract["execution"]["maximum_epochs"]),
        update_limit=int(contract["execution"]["maximum_updates"]), create=True,
    )
    progress.append("AUTHORITY_READY"); progress.append("WAITING_FOR_GPU")
    with gpu_pair_environment(contract["execution"], os.environ.copy()) as environment:
        require_no_conflicting_gpu_workload()
        result = perform_locked_transport_preflight(
            environment, contract["execution"], ROOT, progress)
    return {"status": "PASS", "authority_id": authority["identity"],
            "run_id": training_run_id(authority), "transport": result,
            "log": str(progress.transport_path)}


def log_committed_worker_event(progress: RunProgress, request: dict) -> None:
    if request["message_type"] != "EVENT_PROPOSAL":
        return
    body = request["body"]; event_type = body["event_type"]; payload = body["payload"]
    if event_type == "EPOCH_STARTED":
        progress.append("TRAINING", epoch=payload["epoch"], update=payload["starting_optimizer_update"])
    elif event_type == "PROGRESS_SUMMARY_COMMITTED":
        if any(key not in payload for key in
               ("mean_training_loss", "ending_learning_rate", "epoch_wall_seconds")):
            raise TrainingControllerError("S09_EPOCH_PROGRESS_METRICS_MISSING")
        progress.append("TRAINING", epoch=payload["ending_epoch"], update=payload["last_update"],
                        training_loss=payload["mean_training_loss"],
                        learning_rate=payload["ending_learning_rate"])
    elif event_type == "EARLY_STOPPING_UPDATED":
        progress.append("TRAINING", patience_used=payload["events_without_improvement"],
                        best_checkpoint_id=payload.get("best_checkpoint_id"))
    elif event_type == "TRAINING_COMPLETED":
        status = "EARLY_STOPPED" if payload["reason"] == "EARLY_STOPPING_PATIENCE" else "COMPLETED"
        progress.append(status, epoch=payload["completed_epoch"], update=payload["optimizer_update"])
    elif event_type == "TRAINING_FAILED":
        progress.append("FAILED")


def startup_inputs(contract: dict, authority: dict | None = None) -> StartupInputs:
    parents = dict(contract["parents"])
    parents["scientific_revision_token"] = contract["source"]["scientific_revision_token"]
    if authority is not None and authority["content"]["scientific"]["phase"] == "COMPARISON":
        parents["ofat_winner_id"] = authority["content"]["parents"].get("ofat_winner_id")
    return StartupInputs(
        fuse_root=ROOT, dissertation_root=Path.home() / "dhnyu-masters-dissertation",
        retirement_manifest=Path(contract["roots"]["retirement_manifest"]),
        experiment_plan=Path(contract["roots"]["experiment_plan"]),
        production_cache_root=Path(contract["roots"]["production_cache"]),
        production_cache_acceptance=Path(contract["roots"]["production_cache_acceptance"]),
        writable_root=Path(contract["roots"]["writable_runs"]),
        immutable_root=Path(contract["roots"]["immutable_publication"]),
        expected_dissertation_commit=contract["source"].get("dissertation_commit_provenance"),
        expected_retirement_id=contract["parents"]["retirement_id"],
        expected_experiment_plan_id=contract["parents"]["experiment_plan_id"],
        expected_cache_id=contract["parents"]["production_cache_id"],
        expected_cache_acceptance_id=contract["parents"]["production_cache_acceptance_id"],
        expected_cache_manifest_sha256=contract["production_cache_manifest_sha256"],
        expected_parents=parents,
    )


def run(args: argparse.Namespace) -> dict:
    authority = load(args.authority); validate_training_authority(authority)
    content = authority["content"]
    contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
    require_current_contract_ready(contract)
    progress = progress_logger(authority, contract)
    had_progress_history = progress.run_path.is_file()
    progress.append("AUTHORITY_READY")
    if args.noncanonical_pilot:
        output_root = Path(args.output).resolve()
        temporary_root = Path(tempfile.gettempdir()).resolve()
        if temporary_root not in output_root.parents or "--mode bounded-pilot" not in args.science_worker_command:
            raise TrainingControllerError("NONCANONICAL_PILOT_SCOPE_INVALID")
    else:
        accepted_ids, accepted_hashes = accepted_scientific_configurations(
            Path(contract["roots"]["immutable_publication"]) / "canonical", contract["roots"]["eligibility_snapshot"])
        validate_startup(authority, startup_inputs(contract, authority), accepted_hashes=accepted_hashes,
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
        reconciliation_resume = False
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
            progress.append("INTERRUPTED", epoch=boundary["completed_epoch"],
                            update=boundary["optimizer_update"],
                            latest_checkpoint_id=None if latest is None else latest["payload"]["checkpoint_id"])
            state = controller.replay()
        if state.operational_state == "INTERRUPTED_RESUMABLE" and not controller.resume_allowed():
            raise TrainingControllerError("EXACT_RESUME_EVIDENCE_REQUIRED")
        reconciliation_resume = state.operational_state == "INTERRUPTED_RESUMABLE"
        if state.operational_state not in {"AUTHORIZED", "INTERRUPTED_RESUMABLE"}:
            raise TrainingControllerError("RUN_NOT_STARTABLE_FROM_REPLAY_STATE")
        controller.append("RUN_STARTING", {
            "owner_id": "training-controller", "execution_environment_digest": authority["content_sha256"],
            "training_lock_key": content["scientific_run_key"],
        }, occurred_at=now())
        command = shlex.split(args.science_worker_command)
        staging_root = run_root / "staging"; checkpoint_root = run_root / "checkpoints"
        staging_root.mkdir(parents=True, exist_ok=True); checkpoint_root.mkdir(parents=True, exist_ok=True)
        latest = next((event for event in reversed(read_ledger(controller.ledger_root).events)
                       if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"), None)
        if reconciliation_resume:
            if latest is None:
                raise TrainingControllerError("S09_RESUME_CHECKPOINT_REQUIRED")
            if not had_progress_history:
                raise TrainingControllerError("S09_RESUME_PROGRESS_LOG_REQUIRED")
            progress.append("RESUMING", epoch=latest["payload"]["completed_epoch"],
                            update=latest["payload"]["optimizer_update"],
                            latest_checkpoint_id=latest["payload"]["checkpoint_id"],
                            latest_checkpoint_path=str(checkpoint_root / latest["payload"]["checkpoint_id"] / "checkpoint.pt"))
        environment = os.environ.copy()
        environment.update({
            "FUSE_TRAINING_RUN_ID": controller.run_id,
            "FUSE_TRAINING_STAGING_ROOT": str(staging_root),
            "FUSE_TRAINING_CHECKPOINT_ROOT": str(checkpoint_root),
            "FUSE_TRAINING_RESUME_CHECKPOINT": "" if latest is None else
                str(checkpoint_root / latest["payload"]["checkpoint_id"] / "checkpoint.pt"),
            "FUSE_TRAINING_RESUME_CHECKPOINT_ID": "" if latest is None else latest["payload"]["checkpoint_id"],
        })
        stdout_stream = progress.stdout_path.open("ab")
        stderr_stream = progress.stderr_path.open("ab")
        progress.append("WAITING_FOR_GPU")
        try:
            with gpu_pair_environment(contract["execution"], environment) as locked_environment:
                environment.update(locked_environment)
                require_no_conflicting_gpu_workload()
                process = launch_formal_worker_after_preflight(
                    command, environment, contract["execution"], ROOT, progress,
                    stdout=subprocess.PIPE, stderr=stderr_stream)
                controller.append("RUN_STARTED", {"process_id": str(process.pid), "world_size": 2,
                                                   "runtime_digest": authority["content_sha256"]}, occurred_at=now())
                progress.append("TRAINING")
                assert process.stdout is not None and process.stdin is not None
                for raw in process.stdout:
                    stdout_stream.write(raw); stdout_stream.flush(); os.fsync(stdout_stream.fileno())
                    request = None
                    try:
                        request = parse_canonical_json(raw, json_line=True)
                        validate_worker_message(request)
                        if request["message_type"] == "CHECKPOINT_COMMIT_REQUEST":
                            body = request["body"]
                            progress.append("VALIDATING", epoch=body["completed_epoch"],
                                            update=body["optimizer_update"],
                                            validation_loss=body["validation_retrieval_loss"],
                                            validation_margin=body["mean_source_separation_margin"])
                        response = controller.handle_worker_request(
                            request, staging_root=staging_root, checkpoint_root=checkpoint_root)
                        if request["message_type"] == "CHECKPOINT_COMMIT_REQUEST":
                            progress.append("CHECKPOINT_COMMITTED",
                                            **validation_progress(request["body"], response["body"], checkpoint_root))
                        elif request["message_type"] == "FAILURE_REPORT":
                            progress.append("FAILED")
                        else:
                            log_committed_worker_event(progress, request)
                    except Exception as error:
                        request_id = request.get("request_id", "p9req_" + "0" * 24) if isinstance(request, dict) else "p9req_" + "0" * 24
                        response = worker_response(request_id, status="REJECTED",
                                                   error_code=type(error).__name__, message=str(error)[:512])
                    process.stdin.write(canonical_json_line(response)); process.stdin.flush()
                    if response["message_type"] == "NACK": process.kill(); break
                process.stdin.close(); code = process.wait()
        except BaseException:
            progress.append("FAILED")
            raise
        finally:
            stdout_stream.close(); stderr_stream.close()
        stderr = progress.stderr_path.read_text(encoding="utf-8", errors="replace")
        state = controller.replay()
        if code != 0:
            if state.operational_state == "TRAINING_FAILED":
                if progress.state.get("status") != "FAILED":
                    progress.append("FAILED")
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
            progress.append("INTERRUPTED", epoch=boundary["completed_epoch"],
                            update=boundary["optimizer_update"],
                            latest_checkpoint_id=None if not exact else
                                next(event["payload"]["checkpoint_id"] for event in reversed(events)
                                     if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"))
            raise TrainingControllerError(f"SCIENCE_WORKER_INTERRUPTED: {stderr[-1000:]}")
        if controller.replay().scientific_state != "COMPLETE":
            raise TrainingControllerError("SCIENCE_WORKER_EXITED_WITHOUT_TRAINING_COMPLETED")
        manifest = controller.close()
        result = {"schema_version": "2.0.0", "artifact_type": "training_training_execution",
                  "status": "COMPLETE", "run_id": controller.run_id,
                  "authority_id": authority["identity"], "authority_hash": authority["content_sha256"],
                  "scientific_run_key": content["scientific_run_key"],
                  "ledger_root": str(controller.ledger_root), "ledger_manifest": str(manifest),
                  "checkpoint_root": str(checkpoint_root), "evaluation_consumption_count": 0}
        result_path = run_root / "training_execution.json"
        result_path.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        result["training_execution"] = str(result_path)
        if progress.state.get("status") != "COMPLETED":
            progress.append("COMPLETED")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument(
        "mode", choices=("validate", "preflight", "transport-preflight", "run"))
    parser.add_argument("--authority", required=True); parser.add_argument("--contract", required=True)
    parser.add_argument("--output", default=""); parser.add_argument("--science-worker-command", default="")
    parser.add_argument("--log-root", default="")
    parser.add_argument("--noncanonical-pilot", action="store_true")
    args = parser.parse_args()
    if args.mode == "validate":
        authority = load(args.authority); validate_training_authority(authority)
        print(json.dumps({"status": "PASS", "authority_id": authority["identity"]}, sort_keys=True))
    elif args.mode == "preflight":
        authority = load(args.authority); contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
        require_current_contract_ready(contract)
        accepted_ids, accepted_hashes = accepted_scientific_configurations(
            Path(contract["roots"]["immutable_publication"]) / "canonical", contract["roots"]["eligibility_snapshot"])
        result = validate_startup(authority, startup_inputs(contract, authority), accepted_hashes=accepted_hashes,
                                  accepted_configuration_ids=accepted_ids, cuda_devices=visible_gpu_count())
        print(json.dumps({"status": "PASS", "authority_id": authority["identity"], **result}, sort_keys=True))
    elif args.mode == "transport-preflight":
        if not args.log_root:
            parser.error("transport-preflight requires --log-root")
        print(json.dumps(disposable_transport_preflight(args), sort_keys=True))
    else:
        if not args.output or not args.science_worker_command: parser.error("run requires output and science worker command")
        print(json.dumps(run(args), sort_keys=True))


if __name__ == "__main__": main()
