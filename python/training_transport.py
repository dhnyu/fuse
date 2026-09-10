"""Canonical locked GPU/NCCL transport boundary for formal S09 execution."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from training_controller import TrainingControllerError


TRANSPORT_ENVIRONMENT_KEYS = (
    "CUDA_VISIBLE_DEVICES",
    "NCCL_P2P_DISABLE",
    "NCCL_IB_DISABLE",
)


def formal_transport_contract(execution: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return the one supported formal two-GPU transport contract."""
    devices = tuple(int(value) for value in execution.get("selected_gpu_indices", ()))
    transport = execution.get("transport")
    if devices != (0, 1):
        raise TrainingControllerError("S09_FORMAL_GPU_DEVICES_MUST_BE_0_1")
    if int(execution.get("world_size", -1)) != 2:
        raise TrainingControllerError("S09_FORMAL_WORLD_SIZE_MUST_BE_TWO")
    if execution.get("backend") != "nccl":
        raise TrainingControllerError("S09_FORMAL_BACKEND_MUST_BE_NCCL")
    if not isinstance(transport, Mapping):
        raise TrainingControllerError("S09_NCCL_TRANSPORT_CONTRACT_REQUIRED")
    p2p = transport.get("p2p_disable")
    ib = transport.get("ib_disable")
    timeout = transport.get("preflight_timeout_seconds")
    if p2p != "1":
        raise TrainingControllerError("S09_NCCL_P2P_DISABLE_MUST_BE_ONE")
    if ib != "1":
        raise TrainingControllerError("S09_NCCL_IB_DISABLE_MUST_BE_ONE")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 5 <= float(timeout) <= 120:
        raise TrainingControllerError("S09_NCCL_PREFLIGHT_TIMEOUT_INVALID")
    return {
        "devices": devices,
        "world_size": 2,
        "backend": "nccl",
        "preflight_timeout_seconds": float(timeout),
        "environment": {
            "CUDA_VISIBLE_DEVICES": "0,1",
            "NCCL_P2P_DISABLE": "1",
            "NCCL_IB_DISABLE": "1",
        },
    }


def validate_formal_transport_environment(
        environment: Mapping[str, str], execution: Mapping[str, Any]) -> dict[str, Any]:
    contract = formal_transport_contract(execution)
    for key, expected in contract["environment"].items():
        if environment.get(key) != expected:
            raise TrainingControllerError(f"S09_FORMAL_TRANSPORT_ENVIRONMENT_MISMATCH_{key}")
    return contract


@contextmanager
def gpu_pair_environment(execution: Mapping[str, Any], base_environment: Mapping[str, str] | None = None):
    """Hold all GPU locks while yielding the exact validated formal transport environment."""
    contract = formal_transport_contract(execution)
    root = Path(str(execution.get("gpu_lock_root", "")))
    timeout = execution.get("gpu_lock_timeout_seconds")
    if not root.is_absolute() or isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
        raise TrainingControllerError("S09_GPU_LOCK_CONTRACT_INVALID")
    root.mkdir(parents=True, exist_ok=True)
    streams = []
    deadline = time.monotonic() + float(timeout)
    try:
        for name in ("gpu_pair.lock", *(f"gpu{device}.lock" for device in contract["devices"])):
            stream = (root / name).open("a+")
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        stream.close()
                        raise TrainingControllerError("S09_GPU_LOCK_UNAVAILABLE")
                    time.sleep(0.1)
            streams.append(stream)
        environment = dict(os.environ if base_environment is None else base_environment)
        environment.update(contract["environment"])
        validate_formal_transport_environment(environment, execution)
        yield environment
    finally:
        for stream in reversed(streams):
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()


def require_no_conflicting_gpu_workload(
        check_output: Callable[..., str] = subprocess.check_output) -> None:
    """Fail before preflight if either host GPU already has a compute process."""
    try:
        output = check_output(
            ["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TrainingControllerError("S09_GPU_WORKLOAD_INSPECTION_FAILED") from error
    if any(line.strip() for line in output.splitlines()):
        raise TrainingControllerError("S09_CONFLICTING_GPU_COMPUTE_WORKLOAD")


def nccl_preflight_command(repository_root: str | Path, timeout_seconds: float) -> list[str]:
    script = Path(repository_root).resolve() / "python/ddp_nccl_transport_preflight.py"
    if not script.is_file():
        raise TrainingControllerError("S09_NCCL_PREFLIGHT_SCRIPT_MISSING")
    return [
        sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
        str(script), "--timeout-seconds", format(float(timeout_seconds), "g"),
    ]


def run_nccl_transport_preflight(
        repository_root: str | Path, execution: Mapping[str, Any], environment: Mapping[str, str], *,
        popen_factory: Callable[..., Any] = subprocess.Popen) -> dict[str, Any]:
    """Run the tiny two-rank transport probe under the exact formal worker environment."""
    contract = validate_formal_transport_environment(environment, execution)
    command = nccl_preflight_command(repository_root, contract["preflight_timeout_seconds"])
    started = time.monotonic()
    process = popen_factory(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=dict(environment), text=True)
    timeout = contract["preflight_timeout_seconds"] + 10.0
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise TrainingControllerError("S09_NCCL_PREFLIGHT_PROCESS_TIMEOUT") from error
    if process.returncode != 0:
        detail = (stderr or stdout or "")[-1000:]
        raise TrainingControllerError(f"S09_NCCL_PREFLIGHT_FAILED: {detail}")
    try:
        result = json.loads(stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise TrainingControllerError("S09_NCCL_PREFLIGHT_RESULT_INVALID") from error
    required = {
        "process_group_initialization": "PASS",
        "rank_device_assignment": "PASS",
        "allreduce": "PASS",
        "allgather": "PASS",
        "ddp_construction": "PASS",
        "process_group_destruction": "PASS",
    }
    if (result.get("status") != "PASS" or result.get("backend") != "nccl"
            or result.get("world_size") != 2 or result.get("stages") != required
            or result.get("environment") != contract["environment"]):
        raise TrainingControllerError("S09_NCCL_PREFLIGHT_RESULT_MISMATCH")
    return {
        **result,
        "elapsed_seconds": time.monotonic() - started,
        "python_executable": sys.executable,
        "command": command,
    }


def perform_locked_transport_preflight(
        environment: Mapping[str, str], execution: Mapping[str, Any],
        repository_root: str | Path, progress: Any, *,
        preflight_runner: Callable[..., dict[str, Any]] = run_nccl_transport_preflight) -> dict[str, Any]:
    """Run and record the preflight while the caller retains all GPU locks."""
    contract = validate_formal_transport_environment(environment, execution)
    base_record = {
        "selected_gpus": list(contract["devices"]),
        "world_size": contract["world_size"],
        "backend": contract["backend"],
        "environment": contract["environment"],
        "python_executable": sys.executable,
    }
    progress.append("NCCL_PREFLIGHT")
    progress.append_transport({**base_record, "status": "STARTED"})
    try:
        result = preflight_runner(repository_root, execution, environment)
    except BaseException as error:
        progress.append_transport({**base_record, "status": "FAILED", "error": str(error)[:1000]})
        raise
    progress.append_transport({**base_record, **result, "status": "PASS"})
    return result


def launch_formal_worker_after_preflight(
        command: Iterable[str], environment: Mapping[str, str], execution: Mapping[str, Any],
        repository_root: str | Path, progress: Any, *, stdout: Any, stderr: Any,
        preflight_runner: Callable[..., dict[str, Any]] = run_nccl_transport_preflight,
    popen_factory: Callable[..., Any] = subprocess.Popen) -> Any:
    """Permit worker launch only after the locked exact-environment preflight passes."""
    perform_locked_transport_preflight(
        environment, execution, repository_root, progress,
        preflight_runner=preflight_runner,
    )
    progress.append("PREPARING")
    return popen_factory(list(command), stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                         env=dict(environment))
