"""Pure runtime safety and publication contracts for I21 training."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import torch

from prototype_dataloader import canonical_json_bytes, sha256_file
from prototype_validation import replay_early_stopping as replay_validation_early_stopping
from prototype_validation import NEW_METRIC_KEYS, NEW_SELECTION_RULE


TERMINAL_MARKERS = {"early_stopping", "maximum_epochs", "completed"}
CANONICAL_OUTPUTS = {
    "prototype_training_qc.json": "training_qc",
    "validation_history.json": "validation_history",
}


@dataclass(frozen=True)
class TerminalDecision:
    terminal: bool
    reason: str | None
    completed_epoch: int
    optimizer_step: int
    patience: int


@dataclass(frozen=True)
class ResumeSelection:
    path: Path
    state: dict[str, Any]
    decision: TerminalDecision
    post_termination_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ProfilerPolicy:
    enabled: bool = False
    warmup_steps: int = 0
    sampled_steps: tuple[int, ...] = ()
    interval_steps: int = 0
    max_sampled_steps: int = 0

    @classmethod
    def from_config(cls, value: dict[str, Any] | None) -> "ProfilerPolicy":
        value = value or {}
        return cls(
            enabled=bool(value.get("enabled", False)),
            warmup_steps=max(0, int(value.get("warmup_steps", 0))),
            sampled_steps=tuple(sorted({int(step) for step in value.get("sampled_steps", []) if int(step) > 0})),
            interval_steps=max(0, int(value.get("interval_steps", 0))),
            max_sampled_steps=max(0, int(value.get("max_sampled_steps", 0))),
        )

    def should_profile(self, optimizer_step: int) -> bool:
        if not self.enabled or optimizer_step <= self.warmup_steps:
            return False
        selected = optimizer_step in self.sampled_steps
        if self.interval_steps:
            selected = selected or (optimizer_step - self.warmup_steps) % self.interval_steps == 0
        if not selected:
            return False
        eligible = [step for step in self.sampled_steps if step > self.warmup_steps and step <= optimizer_step]
        if self.interval_steps:
            eligible.extend(range(self.warmup_steps + self.interval_steps, optimizer_step + 1, self.interval_steps))
        return self.max_sampled_steps == 0 or len(set(eligible)) <= self.max_sampled_steps


def replay_early_stopping(
    history: Iterable[dict[str, Any]], validation: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | None]:
    patience, selected, _ = replay_validation_early_stopping(history, validation)
    return patience, selected


def checkpoint_completed_epoch(state: dict[str, Any]) -> int:
    marker = state.get("completion") or {}
    if marker.get("epochs_completed") is not None:
        return int(marker["epochs_completed"])
    if state.get("completed_epoch") is not None:
        return int(state["completed_epoch"])
    ranks = state.get("distributed_rank_states") or []
    epochs = {int(value["sampler_epoch"]) + 1 for value in ranks if "sampler_epoch" in value}
    if len(epochs) != 1:
        raise ValueError("checkpoint rank states do not agree on completed epoch")
    return next(iter(epochs))


def terminal_checkpoint_decision(state: dict[str, Any], run_spec: dict[str, Any]) -> TerminalDecision:
    history = list(state.get("validation_history") or [])
    validation = run_spec.get("validation")
    replay_patience, _, replay_metric_state = replay_validation_early_stopping(history, validation)
    saved_patience = int(state.get("early_stopping_patience_state", 0))
    if history and replay_patience != saved_patience:
        raise ValueError(
            f"checkpoint early-stopping replay mismatch: saved={saved_patience} replay={replay_patience}"
        )
    if validation and validation.get("checkpoint_selection") == NEW_SELECTION_RULE:
        if state.get("early_stopping_metric_state") != replay_metric_state:
            raise ValueError("checkpoint early-stopping metric-state replay mismatch")
    completed_epoch = checkpoint_completed_epoch(state)
    threshold = int(run_spec["validation"]["early_stopping_patience_evaluations"])
    maximum_epochs = int(run_spec["optimizer"]["maximum_epochs"])
    marker = state.get("termination")
    if marker is None:
        marker = (state.get("completion") or {}).get("termination")
    reasons = []
    if marker in TERMINAL_MARKERS:
        reasons.append(str(marker))
    if saved_patience >= threshold or replay_patience >= threshold:
        reasons.append("early_stopping")
    if completed_epoch >= maximum_epochs:
        reasons.append("maximum_epochs")
    reason = "early_stopping" if "early_stopping" in reasons else (reasons[0] if reasons else None)
    return TerminalDecision(bool(reasons), reason, completed_epoch, int(state.get("optimizer_step", 0)), saved_patience)


def scientific_parent_hashes(run_spec: dict[str, Any]) -> dict[str, str]:
    names = {
        "dataset": "dataset_manifest", "loader": "dataloader_manifest", "gate": "no_op_gate_manifest",
        "encoder": "encoder_manifest", "augmentation": "augmentation_manifest", "joint": "joint_model_manifest",
        "distributed_joint": "distributed_joint_model_manifest",
    }
    return {name: str(run_spec[key]["sha256"]) for name, key in names.items()}


def validate_checkpoint_lineage(
    state: dict[str, Any], run_spec: dict[str, Any], parents: dict[str, str], world_size: int = 2
) -> None:
    failures = []
    if state.get("run_id") != run_spec.get("run_id"):
        failures.append("run_id")
    if state.get("plan_id") not in (None, run_spec.get("plan_id")):
        failures.append("plan_id")
    if int(state.get("seed", -1)) != int(run_spec.get("seed", -2)):
        failures.append("seed")
    if state.get("scientific_parents") != parents:
        failures.append("scientific_parents")
    if int(state.get("world_size", -1)) != world_size:
        failures.append("world_size")
    if failures:
        raise ValueError(f"foreign checkpoint lineage fields: {', '.join(failures)}")


def _ledger_steps(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if [int(row["optimizer_step"]) for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError(f"non-contiguous optimizer ledger: {path}")
    return rows


def select_resume_checkpoint(
    paths: Iterable[Path], run_spec: dict[str, Any], parents: dict[str, str], ledger_path: Path | None = None
) -> ResumeSelection | None:
    ledger = _ledger_steps(ledger_path)
    audited: list[tuple[Path, TerminalDecision]] = []
    for path in paths:
        match = re.fullmatch(r"epoch-(\d+)\.pt", path.name)
        if match is None:
            continue
        state = torch.load(path, map_location="cpu", weights_only=False)
        validate_checkpoint_lineage(state, run_spec, parents)
        decision = terminal_checkpoint_decision(state, run_spec)
        if int(match.group(1)) != decision.completed_epoch:
            raise ValueError(f"checkpoint filename/state epoch mismatch: {path}")
        audited.append((path, decision))
        del state
    if not audited:
        return None
    audited.sort(key=lambda item: (item[1].completed_epoch, item[1].optimizer_step, item[0].name))
    terminals = [item for item in audited if item[1].terminal]
    selected = terminals[0] if terminals else audited[-1]
    if selected[1].optimizer_step > len(ledger):
        raise ValueError(f"selected checkpoint step exceeds optimizer ledger: {selected[0]}")
    if selected[1].optimizer_step and int(ledger[selected[1].optimizer_step - 1]["epoch"]) != selected[1].completed_epoch:
        raise ValueError(f"selected checkpoint epoch disagrees with optimizer ledger: {selected[0]}")
    later = tuple(item[0] for item in audited if terminals and item[1].completed_epoch > selected[1].completed_epoch)
    state = torch.load(selected[0], map_location="cpu", weights_only=False)
    return ResumeSelection(selected[0], state, selected[1], later)


def output_role(record: dict[str, Any]) -> str:
    name = Path(record.get("relative_path") or record.get("path") or "").name
    try:
        return CANONICAL_OUTPUTS[name]
    except KeyError as error:
        raise ValueError(f"foreign acceptance output role/path: {name}") from error


def validate_output_records(records: Iterable[dict[str, Any]], root: Path | None = None) -> None:
    values = list(records)
    roles = [output_role(value) for value in values]
    if sorted(roles) != sorted(CANONICAL_OUTPUTS.values()) or len(roles) != len(set(roles)):
        raise ValueError("acceptance outputs must contain each canonical role exactly once")
    for value in values:
        raw = value.get("relative_path") or value.get("path")
        path = (root / raw if root is not None and value.get("relative_path") else Path(raw)).resolve()
        if root is not None and path.parent != root.resolve():
            raise ValueError(f"foreign acceptance output path: {path}")
        if not path.is_file() or path.stat().st_size != int(value["size_bytes"]) or sha256_file(path) != value["sha256"]:
            raise ValueError(f"acceptance output checksum mismatch: {path}")


def format_schema_errors(manifest: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(manifest), key=lambda item: list(item.absolute_path))
    return [{
        "json_path": "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path),
        "message": error.message, "validator": error.validator, "expected": error.validator_value,
    } for error in errors]


def validate_acceptance_manifest(
    manifest: dict[str, Any], schema: dict[str, Any], run_spec: dict[str, Any], parents: dict[str, str]
) -> None:
    errors = format_schema_errors(manifest, schema)
    dynamic = []
    for key in ("plan_id", "run_id"):
        if manifest.get(key) != run_spec.get(key):
            dynamic.append({"json_path": f"$.{key}", "message": "does not match run spec", "expected": run_spec.get(key)})
    scientific = manifest.get("scientific_identity") or {}
    if scientific.get("plan_id") != run_spec.get("plan_id") or scientific.get("run_id") != run_spec.get("run_id"):
        dynamic.append({"json_path": "$.scientific_identity", "message": "plan/run does not match run spec"})
    if scientific.get("parents") != parents:
        dynamic.append({"json_path": "$.scientific_identity.parents", "message": "does not match direct parents", "expected": parents})
    if run_spec.get("validation", {}).get("checkpoint_selection") == NEW_SELECTION_RULE:
        if manifest.get("schema_version") != "2.0.0":
            dynamic.append({"json_path": "$.schema_version", "message": "new validation contract requires 2.0.0"})
        for key in ("validation_implementation_sha256", "scheduler_implementation_sha256"):
            if not isinstance(scientific.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", scientific[key]):
                dynamic.append({"json_path": f"$.scientific_identity.{key}", "message": "missing scientific implementation hash"})
        for key, expected in (("validation_contract", run_spec.get("validation")),
                              ("optimizer_contract", run_spec.get("optimizer"))):
            if scientific.get(key) != expected:
                dynamic.append({"json_path": f"$.scientific_identity.{key}", "message": "does not match run spec", "expected": expected})
        required_metrics = set(NEW_METRIC_KEYS)
        for index, value in enumerate(manifest.get("validation_history", [])):
            missing = required_metrics.difference(value)
            if missing:
                dynamic.append({"json_path": f"$.validation_history[{index}]", "message": f"missing new metrics: {sorted(missing)}"})
    try:
        output_role_values = [output_role(value) for value in manifest.get("outputs", [])]
        if sorted(output_role_values) != sorted(CANONICAL_OUTPUTS.values()) or len(output_role_values) != len(set(output_role_values)):
            raise ValueError("missing or duplicate canonical output role")
    except ValueError as error:
        dynamic.append({"json_path": "$.outputs", "message": str(error)})
    if errors or dynamic:
        raise ValueError("acceptance manifest validation failed: " + json.dumps(errors + dynamic, sort_keys=True))


def atomic_publish(stage: Path, final: Path, names: Iterable[str]) -> str:
    names = tuple(names)
    if final.exists():
        for name in names:
            if not (final / name).is_file() or sha256_file(final / name) != sha256_file(stage / name):
                raise FileExistsError(f"same I21 acceptance ID has different content: {final}")
        shutil.rmtree(stage)
        return "identical_reuse"
    os.replace(stage, final)
    return "new_publish"


def find_existing_acceptance(
    acceptance_root: Path, run_spec: dict[str, Any], selection: ResumeSelection, schema: dict[str, Any], manifest_name: str
) -> Path | None:
    parents = scientific_parent_hashes(run_spec)
    matches = []
    for path in sorted(acceptance_root.glob(f"*/{manifest_name}")):
        manifest = json.loads(path.read_text())
        if manifest.get("run_id") != run_spec.get("run_id") or manifest.get("plan_id") != run_spec.get("plan_id"):
            continue
        if manifest.get("final_checkpoint", {}).get("sha256") != sha256_file(selection.path):
            continue
        validate_acceptance_manifest(manifest, schema, run_spec, parents)
        records = manifest["outputs"]
        validate_output_records(records, path.parent)
        matches.append(path.parent)
    if len(matches) > 1:
        raise RuntimeError(f"multiple accepted terminal bundles for one run/checkpoint: {matches}")
    return matches[0] if matches else None
