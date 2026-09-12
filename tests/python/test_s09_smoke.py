"""CPU-only contracts for nonpublishing qualification; no GPU subprocesses."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
import torch

import s09_smoke as smoke


def assert_exited(pid):
    """SIGKILL delivery is asynchronous; allow bounded kernel scheduling latency."""
    path = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not path.exists() or path.read_text().split()[2] == "Z":
            return
        time.sleep(.01)
    pytest.fail(f"child {pid} survived process-group cleanup")


@pytest.fixture
def output(tmp_path, monkeypatch):
    root = tmp_path / "smoke"
    root.mkdir()
    monkeypatch.setattr(smoke, "SMOKE_ROOT", root)
    return root / "case"


@pytest.fixture
def plan():
    # A small current scientific fixture, not historical S09 execution evidence.
    main = dict(d=128, d_c=128, K_aug=8, augmentation_intensity=1.0,
                ema_momentum=.999, peak_learning_rate=.001)
    rows = [{**main, "configuration_id": name} for name in smoke.OFAT]
    for index, changes in {1: dict(d=64, d_c=64), 2: dict(d=256, d_c=256),
                           3: dict(K_aug=4), 4: dict(K_aug=16),
                           5: dict(augmentation_intensity=.5), 6: dict(augmentation_intensity=2),
                           7: dict(ema_momentum=.99), 8: dict(peak_learning_rate=.002),
                           9: dict(peak_learning_rate=.003), 10: dict(peak_learning_rate=.005)}.items():
        rows[index].update(changes)
    return {"hyperparameter_configurations": rows,
            "comparison_configurations": [{"name": n} for n in smoke.COMPARISONS]}


def test_exact_order():
    assert len(smoke.CASES) == len(set(smoke.CASES)) == 28
    assert smoke.COMPARISONS == ("FM", "A1", "A2", "A3", "A4", "A5", "SSV", "DS", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9")
    assert smoke.OFAT[0] == "main" and smoke.OFAT[-1] == "ofat_peak_learning_rate_0.005"


@pytest.mark.parametrize("name", smoke.CASES)
def test_config_resolution(plan, name):
    original = copy.deepcopy(plan)
    matrix, meta = smoke.case_matrix(plan, name)
    assert plan == original
    assert len(matrix["hyperparameter_configurations"]) == 11
    assert meta["seed"] == smoke.smoke_seed(name)
    assert meta["rank_seeds"] == [meta["seed"], meta["seed"] + 1]
    assert meta["formal_authorized"] is False
    if name in smoke.COMPARISONS:
        assert meta["hyperparameter_basis"] == "SMOKE_ONLY_COMPARISON_HYPERPARAMETERS"
        assert meta["hyperparameters"] == {k: original["hyperparameter_configurations"][0][k] for k in meta["hyperparameters"]}
        assert meta["family"] == name
    assert smoke.case_matrix(plan, name) == (matrix, meta)


def test_inventory_and_seed_fail_closed(plan):
    plan["hyperparameter_configurations"].reverse()
    with pytest.raises(ValueError, match="INVENTORY"):
        smoke.case_matrix(plan, "main")
    with pytest.raises(ValueError):
        smoke.smoke_seed("unknown")
    assert len({smoke.smoke_seed(n) for n in smoke.CASES}) == 28


@pytest.mark.parametrize("name", ["checkpoint.pt", "authority.json", "acceptance.json", "ledger.json", "winner.json", "campaign_status.tsv", "current_status.txt"])
def test_production_names_rejected(output, name):
    with pytest.raises(ValueError):
        smoke.safe_output(output / name)


def test_output_escape_symlink_and_no_overwrite(output):
    with pytest.raises(ValueError):
        smoke.safe_output(output.parent.parent / "fuse-training-s09")
    with pytest.raises(ValueError):
        smoke.safe_output(output / ".." / "escape")
    output.symlink_to(output.parent.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        smoke.safe_output(output / "data.json")
    target = output.parent / "ok.json"
    smoke.write_json(target, {"ok": True})
    with pytest.raises(FileExistsError):
        smoke.write_json(target, {"ok": False})


def test_gradient_audit():
    model = torch.nn.Linear(2, 2)
    with pytest.raises(ValueError, match="GRADIENT"):
        smoke.gradient_audit(model)
    model(torch.ones(2, 2)).sum().backward()
    assert smoke.gradient_audit(model)["status"] == "PASS"
    model.weight.grad[0, 0] = float("nan")
    with pytest.raises(ValueError, match="GRADIENT"):
        smoke.gradient_audit(model)


def test_one_step_observer_and_queue():
    state = SimpleNamespace(optimizer=SimpleNamespace(step=lambda: None),
                            scheduler=SimpleNamespace(advance=lambda: None, completed_updates=1),
                            model=SimpleNamespace(update_target=lambda x: None, parameters=lambda: [], target=torch.nn.Identity()),
                            queue={"enqueue_count":64, "valid_count":64, "pointer":64, "values":torch.zeros(64,2)})
    with smoke.step_counters(state) as counts:
        state.optimizer.step(); state.scheduler.advance(); state.model.update_target(.999)
    smoke.assert_step_state(state, counts)
    with pytest.raises(ValueError, match="ONE_STEP"):
        smoke.assert_step_state(state, {**counts, "optimizer":2})
    state.queue["enqueue_count"] = 32
    with pytest.raises(ValueError, match="QUEUE"):
        smoke.assert_step_state(state, counts)


@pytest.mark.parametrize("family", ["FM", "DS"])
def test_validation_actual_assembly(monkeypatch, family):
    import training_family_inputs as fi
    observed = []
    def assemble(values, records):
        observed.extend(records)
        return {"size":len(records)}, None, []
    monkeypatch.setattr(fi, "assemble_family_batch", assemble)
    monkeypatch.setattr(fi, "family_encoder_batch", lambda x: x)
    class Model(torch.nn.Module):
        def forward(self, batch, geometry, ds):
            assert (ds is not None) == (family == "DS")
            return {"scene_embedding":torch.ones(batch["size"], 128)}
    roles = []
    def raster(batch, role, device):
        roles.append(role)
        return torch.ones(batch["size"], 26, 100, 100)
    values = {"family":family, "data":SimpleNamespace(validation_scenes=[str(i).zfill(3) for i in range(1000)]),
              "ds_raster_cache":SimpleNamespace(batch=raster), "model_config":{"model":{"d":128}}}
    state = SimpleNamespace(model=SimpleNamespace(online=Model()))
    result = smoke.validation_smoke(state, values, torch.device("cpu"))
    assert result["query_count"] == result["gallery_count"] == 32
    assert len(observed) == 64 and {r[0] for r in observed} == {"validation_query","validation_gallery"}
    assert result["output_shape"] == [32,128] and result["scientific_metric"] is False
    if family == "DS":
        assert roles == ["validation_query"] * 4 + ["validation_gallery"] * 4


def test_timeout_kills_entire_process_group(output):
    output.mkdir()
    pidfile = output / "child.pid"
    command = [sys.executable, "-c", "import subprocess,time,pathlib; p=subprocess.Popen(['sleep','60']); pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid)); time.sleep(60)"]
    with pytest.raises(subprocess.TimeoutExpired):
        with smoke.managed_processes() as factory:
            process = factory(command)
            process.wait(timeout=.3)
    assert process.poll() is not None
    child = int(pidfile.read_text())
    assert_exited(child)


def test_interrupt_releases_process():
    with pytest.raises(InterruptedError):
        with smoke.interrupt_guard(), smoke.managed_processes() as factory:
            process = factory(["sleep", "60"])
            os.kill(os.getpid(), signal.SIGTERM)
    assert process.poll() is not None


def test_preflight_failure_never_launches_science(output, plan, monkeypatch):
    import training_transport as tr
    from contextlib import contextmanager
    lock = []
    @contextmanager
    def guard(execution):
        lock.append("held")
        try:
            yield {"CUDA_VISIBLE_DEVICES":"0,1", "NCCL_P2P_DISABLE":"1", "NCCL_IB_DISABLE":"1"}
        finally:
            lock.append("released")
    def preflight(root, execution, env, **kwargs):
        assert lock == ["held"] and env["NCCL_IB_DISABLE"] == "1"
        raise RuntimeError("preflight failed")
    monkeypatch.setattr(tr, "gpu_pair_environment", guard)
    monkeypatch.setattr(tr, "require_no_conflicting_gpu_workload", lambda: None)
    monkeypatch.setattr(tr, "run_nccl_transport_preflight", preflight)
    monkeypatch.setattr(smoke, "ProcessGroup", lambda *a, **k: pytest.fail("science must not launch"))
    inputs = dict(plan=plan, execution={}, runtime_sha="a"*64, cache_root="unused", categories="unused")
    with pytest.raises(RuntimeError, match="preflight failed"):
        smoke.run_case(inputs, "main", output)
    assert lock == ["held", "released"]
    assert json.loads((output/"case_result.json").read_text())["verdict"] == "FAIL"
    assert "FAIL" in (output/"preflight.jsonl").read_text()


def test_no_publication_entrypoints_or_registered_runtime():
    import ast
    import yaml
    tree = ast.parse(Path(smoke.__file__).read_text())
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, (ast.Attribute, ast.Name))}
    assert not calls & {"run_worker", "ControllerClient", "_stage_checkpoint", "publish_documents", "restore_checkpoint", "tar_make", "save"}
    registry = yaml.safe_load((smoke.ROOT / "config/s09_runtime_provenance.yml").read_text())
    assert "s09_smoke" not in str(registry)


def test_validation_deadline():
    with pytest.raises(TimeoutError, match="VALIDATION_TIMEOUT"):
        with smoke.deadline(.01):
            time.sleep(.1)


def test_failed_launcher_kills_lingering_peer(output):
    output.mkdir()
    pidfile = output / "peer.pid"
    command = [sys.executable, "-c", "import subprocess,pathlib; p=subprocess.Popen(['sleep','60']); pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid)); raise SystemExit(1)"]
    with smoke.managed_processes() as factory:
        process = factory(command)
        assert process.wait(timeout=5) == 1
    child = int(pidfile.read_text())
    assert_exited(child)


@pytest.mark.parametrize("failure", [False, True])
def test_worker_environment_and_lock_scope(output, plan, monkeypatch, failure):
    import training_transport as tr
    from contextlib import contextmanager
    locks = []
    execution = {"sentinel":"same contract"}
    seen = []
    @contextmanager
    def guard(config):
        assert config is execution
        locks.append("held")
        try:
            yield {"CUDA_VISIBLE_DEVICES":"0,1", "NCCL_P2P_DISABLE":"1", "NCCL_IB_DISABLE":"1", "FUSE_TRAINING_RESUME_CHECKPOINT":"forbidden"}
        finally:
            locks.append("released")
    def preflight(root, config, env, **kwargs):
        assert locks == ["held"] and config is execution
        seen.append(dict(env))
        return {"status":"PASS"}
    class FakeProcess:
        def __init__(self, command, **kwargs):
            assert locks == ["held"] and kwargs["env"] == seen[0]
            assert "FUSE_TRAINING_RESUME_CHECKPOINT" not in kwargs["env"]
            assert "--nproc_per_node=2" in command
        def wait(self, timeout):
            if failure:
                raise subprocess.TimeoutExpired("science", timeout)
            meta = smoke.case_matrix(plan, "main")[1]
            for rank in (0,1):
                smoke.write_json(output / f"rank{rank}.json", good_rank(meta, rank))
            return 0
        def terminate_group(self):
            assert locks == ["held"]
            seen.append("cleaned")
    monkeypatch.setattr(tr, "gpu_pair_environment", guard)
    monkeypatch.setattr(tr, "require_no_conflicting_gpu_workload", lambda: None)
    monkeypatch.setattr(tr, "run_nccl_transport_preflight", preflight)
    monkeypatch.setattr(smoke, "ProcessGroup", FakeProcess)
    inputs = dict(plan=plan, execution=execution, runtime_sha="a"*64, cache_root="unused", categories="unused")
    if failure:
        with pytest.raises(subprocess.TimeoutExpired):
            smoke.run_case(inputs, "main", output)
    else:
        assert smoke.run_case(inputs, "main", output)["verdict"] == "PASS"
    assert locks == ["held", "released"] and seen[-1] == "cleaned"


def good_rank(meta, rank):
    return {**meta, "rank":rank, "verdict":"PASS", "runtime_sha":"a"*64,
            "steps":{"optimizer":1,"scheduler":1,"ema":1},
            "queue":{"before":0,"after":64,"enqueued":64},
            "gradients":{"status":"PASS","active":["weight"],"unexpected_unused":[]},
            "training":{"total_loss":1.0}, "validation":{"status":"PASS","finite":True,
                "query_count":32,"gallery_count":32,"output_shape":[32,meta["hyperparameters"]["d"]]}}


def test_result_validation_rejects_partial_and_wrong_counts(plan):
    meta=smoke.case_matrix(plan,"main")[1]
    ranks=[good_rank(meta,r) for r in (0,1)]
    smoke.validate_rank_results(ranks,meta,"a"*64)
    for field in ("queue","steps","gradients","training","validation"):
        invalid=copy.deepcopy(ranks)
        del invalid[0][field]
        with pytest.raises(ValueError):smoke.validate_rank_results(invalid,meta,"a"*64)
    ranks[1]["gradients"]["active"]=["other"]
    with pytest.raises(ValueError,match="STRUCTURE"):
        smoke.validate_rank_results(ranks,meta,"a"*64)


@pytest.mark.parametrize("family,attribute", [("B2","poi_embeddings"),("B3","road_numerical"),
                                             ("B4","building_fusion"),("B8","dem_cnn"),("B9","landcover_cnn")])
def test_forbidden_family_module(family,attribute):
    fake=SimpleNamespace(**{attribute:object()})
    with pytest.raises(ValueError,match="FORBIDDEN_MODULE"):
        smoke.module_audit(fake,family)
