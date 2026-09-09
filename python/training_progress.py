"""Append-only operational progress logging for the formal S09 campaign."""

from __future__ import annotations

import csv
import datetime as dt
import fcntl
import io
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping


class TrainingProgressError(RuntimeError):
    """A fail-closed progress logging contract error."""


TSV_FIELDS = (
    "timestamp", "phase", "config_or_model", "authority_id", "run_id", "status",
    "epoch", "epoch_limit", "update", "update_limit", "training_loss",
    "validation_loss", "validation_margin", "learning_rate", "selection_eligible",
    "best_epoch", "best_validation_loss", "best_validation_margin", "patience_used",
    "patience_limit", "latest_checkpoint_id", "latest_checkpoint_path",
    "best_checkpoint_id", "best_checkpoint_path", "elapsed_seconds",
    "prepared_cache_status", "phase_completed", "phase_total", "winner_configuration",
    "campaign_status",
)
NA = "NA"
TERMINAL_ACCEPTED = "ACCEPTED"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _clean(value: Any) -> str:
    if value is None or value == "":
        return NA
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return format(value, ".17g")
    text = str(value)
    if any(character in text for character in ("\t", "\r", "\n")):
        raise TrainingProgressError("S09_PROGRESS_VALUE_CONTAINS_CONTROL_CHARACTER")
    return text


def _safe_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    if not component:
        raise TrainingProgressError("S09_PROGRESS_FILE_COMPONENT_INVALID")
    return component


def resolve_log_root(repository_root: str | Path, configured: str | Path = "logs/s09") -> Path:
    root = Path(configured)
    return root.resolve() if root.is_absolute() else (Path(repository_root) / root).resolve()


def configured_log_root(repository_root: str | Path, contract: Mapping[str, Any]) -> Path:
    configured = (contract.get("execution") or {}).get("progress_log_root")
    if configured != "logs/s09":
        raise TrainingProgressError("S09_PROGRESS_LOG_ROOT_MUST_BE_LOGS_S09")
    return resolve_log_root(repository_root, configured)


def ensure_log_root(root: str | Path, *, create: bool) -> Path:
    path = Path(root)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise TrainingProgressError(f"S09_PROGRESS_LOG_DIRECTORY_MISSING: {path}")
    probe = path / f".write-probe-{os.getpid()}"
    try:
        with probe.open("xb") as stream:
            stream.write(b"ready\n"); stream.flush(); os.fsync(stream.fileno())
        probe.unlink()
    except OSError as error:
        raise TrainingProgressError(f"S09_PROGRESS_LOG_DIRECTORY_NOT_WRITABLE: {path}") from error
    return path.resolve()


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != TSV_FIELDS:
            raise TrainingProgressError(f"S09_PROGRESS_HEADER_MISMATCH: {path}")
        return list(reader)


def _append_locked(path: Path, row: Mapping[str, str], *, identity: tuple[str, str] | None = None) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = _read_rows(path)
        if identity is not None:
            authority_id, run_id = identity
            if any(item["authority_id"] != authority_id or item["run_id"] != run_id for item in rows):
                raise TrainingProgressError("S09_PROGRESS_RUN_IDENTITY_MISMATCH")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=TSV_FIELDS, delimiter="\t", lineterminator="\n")
        if not rows:
            writer.writeheader()
        writer.writerow(row)
        with path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(buffer.getvalue()); stream.flush(); os.fsync(stream.fileno())
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _atomic_status(root: Path, row: Mapping[str, str]) -> None:
    status_path = root / "current_status.txt"
    lock_path = root / ".current_status.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        elapsed = float(row["elapsed_seconds"]) if row["elapsed_seconds"] != NA else 0.0
        elapsed_text = time.strftime("%H:%M:%S", time.gmtime(max(0.0, elapsed)))
        lines = (
            f"timestamp={row['timestamp']}", f"phase={row['phase']}",
            f"model={row['config_or_model']}", f"authority={row['authority_id']}",
            f"run_id={row['run_id']}", f"status={row['status']}",
            f"epoch={row['epoch']}/{row['epoch_limit']}",
            f"update={row['update']}/{row['update_limit']}",
            f"training_loss={row['training_loss']}", f"validation_loss={row['validation_loss']}",
            f"validation_margin={row['validation_margin']}", f"learning_rate={row['learning_rate']}",
            f"best_epoch={row['best_epoch']}", f"best_validation_loss={row['best_validation_loss']}",
            f"best_validation_margin={row['best_validation_margin']}",
            f"patience={row['patience_used']}/{row['patience_limit']}",
            f"latest_checkpoint={row['latest_checkpoint_id']}",
            f"best_checkpoint={row['best_checkpoint_id']}",
            f"completed={row['phase_completed']}/{row['phase_total']}",
            f"winner={row['winner_configuration']}", f"campaign={row['campaign_status']}",
            f"elapsed={elapsed_text}",
        )
        temporary = root / f".current_status.{os.getpid()}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write("\n".join(lines) + "\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, status_path)
            descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary.exists():
                temporary.unlink()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def campaign_snapshot(rows: list[Mapping[str, str]]) -> dict[str, str]:
    accepted = {phase: set() for phase in ("OFAT", "COMPARISON")}
    winner = NA
    cache_status = NA
    campaign_status = "IN_PROGRESS" if rows else "NOT_STARTED"
    for row in rows:
        phase, status = row.get("phase"), row.get("status")
        if phase in accepted and status == TERMINAL_ACCEPTED:
            accepted[phase].add(row.get("config_or_model", NA))
        if status == "WINNER_SELECTED":
            winner = row.get("winner_configuration", row.get("config_or_model", NA))
        if phase == "CACHE":
            cache_status = status or NA
        if status in {"CAMPAIGN_ACCEPTED", "CAMPAIGN_FAILED"}:
            campaign_status = status
        elif status in {"FAILED", "PREPARED_CACHE_FAILED"}:
            campaign_status = "CAMPAIGN_FAILED"
        elif status == "INTERRUPTED":
            campaign_status = "INTERRUPTED_RESUMABLE"
        elif status in {"AUTHORITY_READY", "WAITING_FOR_GPU", "PREPARING", "TRAINING",
                        "VALIDATING", "CHECKPOINT_COMMITTED", "RESUMING", "COMPLETED",
                        "EARLY_STOPPED"}:
            campaign_status = "IN_PROGRESS"
    return {
        "ofat_completed": str(len(accepted["OFAT"])), "ofat_total": "11",
        "comparison_completed": str(len(accepted["COMPARISON"])), "comparison_total": "17",
        "winner_configuration": winner, "prepared_cache_status": cache_status,
        "campaign_status": campaign_status,
    }


class CampaignProgress:
    """Concurrency-safe writer for campaign and per-run operational progress."""

    def __init__(self, root: str | Path, *, create: bool = False):
        self.root = ensure_log_root(root, create=create)
        self.campaign_path = self.root / "campaign_status.tsv"

    def _campaign_row(self, values: Mapping[str, Any]) -> dict[str, str]:
        existing = _read_rows(self.campaign_path)
        snapshot = campaign_snapshot(existing)
        phase = _clean(values.get("phase"))
        phase_completed = (snapshot["ofat_completed"] if phase == "OFAT" else
                           snapshot["comparison_completed"] if phase == "COMPARISON" else NA)
        phase_total = (snapshot["ofat_total"] if phase == "OFAT" else
                       snapshot["comparison_total"] if phase == "COMPARISON" else NA)
        defaults: dict[str, Any] = {field: NA for field in TSV_FIELDS}
        defaults.update({"timestamp": utc_now(), "prepared_cache_status": snapshot["prepared_cache_status"],
                         "phase_completed": phase_completed, "phase_total": phase_total,
                         "winner_configuration": snapshot["winner_configuration"],
                         "campaign_status": snapshot["campaign_status"]})
        defaults.update(values)
        row = {field: _clean(defaults[field]) for field in TSV_FIELDS}
        projected = campaign_snapshot([*existing, row])
        row.update({"prepared_cache_status": projected["prepared_cache_status"],
                    "winner_configuration": projected["winner_configuration"],
                    "campaign_status": projected["campaign_status"]})
        if row["phase"] == "OFAT":
            row.update(phase_completed=projected["ofat_completed"], phase_total=projected["ofat_total"])
        elif row["phase"] == "COMPARISON":
            row.update(phase_completed=projected["comparison_completed"],
                       phase_total=projected["comparison_total"])
        return row

    def append_campaign(self, status: str, *, phase: str = "CAMPAIGN", **values: Any) -> dict[str, str]:
        row = self._campaign_row({"phase": phase, "status": status, **values})
        _append_locked(self.campaign_path, row)
        snapshot = campaign_snapshot(_read_rows(self.campaign_path))
        row.update({
            "prepared_cache_status": snapshot["prepared_cache_status"],
            "winner_configuration": snapshot["winner_configuration"],
            "campaign_status": snapshot["campaign_status"],
        })
        if row["phase"] == "OFAT":
            row.update(phase_completed=snapshot["ofat_completed"], phase_total=snapshot["ofat_total"])
        elif row["phase"] == "COMPARISON":
            row.update(phase_completed=snapshot["comparison_completed"], phase_total=snapshot["comparison_total"])
        _atomic_status(self.root, row)
        return row


class RunProgress(CampaignProgress):
    def __init__(self, root: str | Path, *, phase: str, config_or_model: str,
                 authority_id: str, run_id: str, patience_limit: int,
                 epoch_limit: int, update_limit: int, create: bool = False,
                 require_existing: bool = False):
        super().__init__(root, create=create)
        self.phase = str(phase); self.config_or_model = str(config_or_model)
        self.authority_id = str(authority_id); self.run_id = str(run_id)
        stem = "_".join(_safe_component(value) for value in
                        (self.phase.lower(), self.config_or_model, self.run_id))
        self.run_path = self.root / f"{stem}.tsv"
        self.stdout_path = self.root / f"{stem}.stdout.log"
        self.stderr_path = self.root / f"{stem}.stderr.log"
        if require_existing and not self.run_path.is_file():
            raise TrainingProgressError("S09_RESUME_PROGRESS_LOG_REQUIRED")
        rows = _read_rows(self.run_path)
        if any(row["authority_id"] != self.authority_id or row["run_id"] != self.run_id for row in rows):
            raise TrainingProgressError("S09_PROGRESS_RUN_IDENTITY_MISMATCH")
        self.state: dict[str, Any] = {field: NA for field in TSV_FIELDS}
        if rows:
            self.state.update(rows[-1])
        self.state.update({"phase": self.phase, "config_or_model": self.config_or_model,
                           "authority_id": self.authority_id, "run_id": self.run_id,
                           "patience_limit": patience_limit, "epoch_limit": epoch_limit,
                           "update_limit": update_limit})
        self.elapsed_offset = float(self.state["elapsed_seconds"]) if self.state["elapsed_seconds"] != NA else 0.0
        self.started = time.monotonic()

    def append(self, status: str, **values: Any) -> dict[str, str]:
        elapsed = self.elapsed_offset + time.monotonic() - self.started
        self.state.update(values)
        self.state.update({"timestamp": utc_now(), "status": status, "elapsed_seconds": elapsed})
        row = {field: _clean(self.state[field]) for field in TSV_FIELDS}
        _append_locked(self.run_path, row, identity=(self.authority_id, self.run_id))
        campaign_row = self._campaign_row(row)
        _append_locked(self.campaign_path, campaign_row)
        snapshot = campaign_snapshot(_read_rows(self.campaign_path))
        row.update({"prepared_cache_status": snapshot["prepared_cache_status"],
                    "winner_configuration": snapshot["winner_configuration"],
                    "campaign_status": snapshot["campaign_status"]})
        if self.phase == "OFAT":
            row.update(phase_completed=snapshot["ofat_completed"], phase_total=snapshot["ofat_total"])
        elif self.phase == "COMPARISON":
            row.update(phase_completed=snapshot["comparison_completed"], phase_total=snapshot["comparison_total"])
        _atomic_status(self.root, row)
        self.state.update(row)
        return row


def validation_progress(body: Mapping[str, Any], response: Mapping[str, Any],
                        checkpoint_root: str | Path) -> dict[str, Any]:
    """Use the exact formal selection/checkpoint values already committed by the controller."""
    selected = bool(body["current_candidate_selected"])
    values: dict[str, Any] = {
        "epoch": body["completed_epoch"], "update": body["optimizer_update"],
        "validation_loss": body["validation_retrieval_loss"],
        "validation_margin": body["mean_source_separation_margin"],
        "selection_eligible": True,
        "patience_used": response["selector_state"]["events_without_improvement"],
        "latest_checkpoint_id": response["checkpoint_id"],
        "latest_checkpoint_path": str(Path(checkpoint_root) / response["checkpoint_id"] / "checkpoint.pt"),
    }
    if selected:
        values.update({"best_epoch": body["completed_epoch"],
                       "best_validation_loss": body["validation_retrieval_loss"],
                       "best_validation_margin": body["mean_source_separation_margin"],
                       "best_checkpoint_id": response["checkpoint_id"],
                       "best_checkpoint_path": str(Path(checkpoint_root) /
                                                   response["checkpoint_id"] / "checkpoint.pt")})
    return values
