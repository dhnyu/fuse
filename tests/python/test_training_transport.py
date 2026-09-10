from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from training_controller import TrainingControllerError  # noqa: E402
from training_transport import (  # noqa: E402
    formal_transport_contract, gpu_pair_environment,
    launch_formal_worker_after_preflight, run_nccl_transport_preflight,
    validate_formal_transport_environment,
)


def execution(lock_root: Path) -> dict:
    return {
        "selected_gpu_indices": [0, 1], "world_size": 2, "backend": "nccl",
        "gpu_lock_root": str(lock_root), "gpu_lock_timeout_seconds": 0.1,
        "transport": {"p2p_disable": "1", "ib_disable": "1",
                      "preflight_timeout_seconds": 30},
    }


def valid_result() -> dict:
    return {
        "status": "PASS", "backend": "nccl", "world_size": 2,
        "environment": {"CUDA_VISIBLE_DEVICES": "0,1", "NCCL_P2P_DISABLE": "1",
                        "NCCL_IB_DISABLE": "1"},
        "stages": {"process_group_initialization": "PASS", "rank_device_assignment": "PASS",
                   "allreduce": "PASS", "allgather": "PASS",
                   "ddp_construction": "PASS",
                   "process_group_destruction": "PASS"},
    }


class Progress:
    def __init__(self):
        self.states = []; self.transport = []

    def append(self, status):
        self.states.append(status)

    def append_transport(self, value):
        self.transport.append(value)


class Process:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout_value = stdout; self.stderr_value = ""; self.returncode = returncode
        self.killed = False; self.pid = 123

    def communicate(self, timeout=None):
        return self.stdout_value, self.stderr_value

    def kill(self):
        self.killed = True


def test_formal_environment_is_exact_and_fail_closed(tmp_path):
    settings = execution(tmp_path)
    contract = formal_transport_contract(settings)
    assert contract["environment"] == {
        "CUDA_VISIBLE_DEVICES": "0,1", "NCCL_P2P_DISABLE": "1", "NCCL_IB_DISABLE": "1"}
    validate_formal_transport_environment(contract["environment"], settings)
    for key in contract["environment"]:
        changed = dict(contract["environment"]); changed.pop(key)
        with pytest.raises(TrainingControllerError, match="ENVIRONMENT_MISMATCH"):
            validate_formal_transport_environment(changed, settings)
        changed = dict(contract["environment"]); changed[key] = "0"
        with pytest.raises(TrainingControllerError, match="ENVIRONMENT_MISMATCH"):
            validate_formal_transport_environment(changed, settings)
    for key, value, message in (
        ("selected_gpu_indices", [1, 0], "GPU_DEVICES"),
        ("world_size", 1, "WORLD_SIZE"), ("backend", "gloo", "BACKEND"),
    ):
        changed = copy.deepcopy(settings); changed[key] = value
        with pytest.raises(TrainingControllerError, match=message):
            formal_transport_contract(changed)


def test_preflight_command_receives_exact_environment_and_collective_result(tmp_path):
    settings = execution(tmp_path); environment = formal_transport_contract(settings)["environment"]
    captured = {}

    def popen(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return Process(json.dumps(valid_result()) + "\n")

    result = run_nccl_transport_preflight(ROOT, settings, environment, popen_factory=popen)
    assert captured["command"][1:5] == [
        "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2"]
    assert "ddp_nccl_transport_preflight.py" in captured["command"][5]
    assert captured["kwargs"]["env"] == environment
    assert result["stages"]["allreduce"] == "PASS"
    assert result["stages"]["allgather"] == "PASS"


def test_preflight_timeout_and_missing_collective_fail_closed(tmp_path):
    settings = execution(tmp_path); environment = formal_transport_contract(settings)["environment"]

    class TimeoutProcess(Process):
        def communicate(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("probe", timeout)
            return "", ""

    with pytest.raises(TrainingControllerError, match="PROCESS_TIMEOUT"):
        run_nccl_transport_preflight(ROOT, settings, environment,
                                     popen_factory=lambda *args, **kwargs: TimeoutProcess(""))
    result = valid_result(); del result["stages"]["allgather"]
    with pytest.raises(TrainingControllerError, match="RESULT_MISMATCH"):
        run_nccl_transport_preflight(
            ROOT, settings, environment,
            popen_factory=lambda *args, **kwargs: Process(json.dumps(result) + "\n"))


def test_worker_launch_is_gated_by_preflight_under_same_locked_environment(tmp_path):
    settings = execution(tmp_path); progress = Progress(); worker_calls = []

    def failed(*args):
        raise TrainingControllerError("probe failed")

    with gpu_pair_environment(settings, {}) as environment:
        with pytest.raises(TrainingControllerError, match="probe failed"):
            launch_formal_worker_after_preflight(
                ["worker"], environment, settings, ROOT, progress,
                stdout=None, stderr=None, preflight_runner=failed,
                popen_factory=lambda *args, **kwargs: worker_calls.append(kwargs))
        blocked = copy.deepcopy(settings); blocked["gpu_lock_timeout_seconds"] = 0
        with pytest.raises(TrainingControllerError, match="LOCK_UNAVAILABLE"):
            with gpu_pair_environment(blocked): pass
    assert worker_calls == []
    assert progress.transport[-1]["status"] == "FAILED"

    captured = {}
    progress = Progress()

    def passed(root, actual_settings, actual_environment):
        captured["preflight_environment"] = dict(actual_environment)
        return valid_result()

    def worker(command, **kwargs):
        captured["worker_environment"] = kwargs["env"]
        return Process("")

    with gpu_pair_environment(settings, {}) as environment:
        launch_formal_worker_after_preflight(
            ["worker"], environment, settings, ROOT, progress,
            stdout=None, stderr=None, preflight_runner=passed, popen_factory=worker)
        blocked = copy.deepcopy(settings); blocked["gpu_lock_timeout_seconds"] = 0
        with pytest.raises(TrainingControllerError, match="LOCK_UNAVAILABLE"):
            with gpu_pair_environment(blocked): pass
    assert captured["preflight_environment"] == captured["worker_environment"]
    assert progress.states == ["NCCL_PREFLIGHT", "PREPARING"]
    assert progress.transport[-1]["status"] == "PASS"

    with gpu_pair_environment(settings, {}) as environment:
        assert environment["NCCL_P2P_DISABLE"] == "1"


@pytest.mark.parametrize("error", [RuntimeError("worker failed"), KeyboardInterrupt()])
def test_gpu_locks_release_on_worker_failure_or_interruption(tmp_path, error):
    settings = execution(tmp_path)
    with pytest.raises(type(error)):
        with gpu_pair_environment(settings, {}):
            raise error
    with gpu_pair_environment(settings, {}) as environment:
        assert environment["CUDA_VISIBLE_DEVICES"] == "0,1"
