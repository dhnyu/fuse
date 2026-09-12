"""Nonpublishing S09 execution qualification; never a scientific campaign.

Uses the dissertation training procedure through training_worker.training_update.
Validation uses the same prepared family assembly, on a labelled smoke subset.
This operator is intentionally outside the formal runtime provenance registry.
"""

from __future__ import annotations

import copy
import csv
import datetime as dt
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from artifact_protocol import canonical_sha256, sha256_file
from training_campaign import COMPARISON_IDS

ROOT = Path(__file__).resolve().parents[1]
SMOKE_ROOT = ROOT / "logs/s09/smoke"
OFAT = ("main", "ofat_d_64", "ofat_d_256", "ofat_K_aug_4", "ofat_K_aug_16",
        "ofat_augmentation_intensity_0.5", "ofat_augmentation_intensity_2.0",
        "ofat_ema_momentum_0.99", "ofat_peak_learning_rate_0.002",
        "ofat_peak_learning_rate_0.003", "ofat_peak_learning_rate_0.005")
COMPARISONS = COMPARISON_IDS
CASES = OFAT + COMPARISONS
SMOKE_SEED = 20260912
CACHE_ID = "s09cache_dc4e9e271e40ffe8ae17967c"
ACCEPTANCE_ID = "s09ca_e2a1882eb206e1b5c930ddd5"
PLAN_ID = "s08plan_7cd58ffb65db3d43fd3fa234"
PLAN_FILE_SHA = "74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789"


def safe_output(path: str | Path) -> Path:
    path = Path(path).absolute()
    base = SMOKE_ROOT.absolute()
    if base not in path.parents:
        raise ValueError("SMOKE_OUTPUT_MUST_BE_BELOW_LOGS_S09_SMOKE")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("SMOKE_OUTPUT_SYMLINK_FORBIDDEN")
    if path.resolve() != path:
        raise ValueError("SMOKE_OUTPUT_NOT_CANONICAL")
    forbidden = ("checkpoint", "authority", "acceptance", "ledger", "winner",
                 "campaign_status", "current_status")
    if any(word in part.lower() for part in path.relative_to(base).parts for word in forbidden):
        raise ValueError("SMOKE_PRODUCTION_ARTIFACT_NAME_FORBIDDEN")
    return path


def write_json(path: Path, value) -> None:
    path = safe_output(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def smoke_seed(name: str) -> int:
    if name not in CASES:
        raise ValueError("UNKNOWN_SMOKE_CASE")
    content = {"namespace": "s09-smoke-only-v1", "root": SMOKE_SEED,
               "sequence": CASES.index(name) + 1, "case": name}
    return int(canonical_sha256(content)[:16], 16) % (2**31 - 2)


def tooling_hashes() -> dict:
    return {str(path.relative_to(ROOT)): sha256_file(path) for path in
            (ROOT / "python/s09_smoke.py", ROOT / "scripts/s09_smoke_matrix.py")}


def case_matrix(plan: dict, name: str) -> tuple[dict, dict]:
    """Adapt S08 rows to the existing worker-value interface, without authorities."""
    from training_configuration import scientific_row_hash
    if tuple(r["configuration_id"] for r in plan["hyperparameter_configurations"]) != OFAT:
        raise ValueError("SMOKE_OFAT_INVENTORY_MISMATCH")
    if {r["name"] for r in plan["comparison_configurations"]} != set(COMPARISONS):
        raise ValueError("SMOKE_COMPARISON_INVENTORY_MISMATCH")
    if name not in CASES:
        raise ValueError("UNKNOWN_SMOKE_CASE")
    matrix = copy.deepcopy(plan)
    rows = matrix["hyperparameter_configurations"]
    comparison = name in COMPARISONS
    if comparison:
        rows[0].update(configuration_id="smoke_" + name, model_family=name)
    configuration_id = "smoke_" + name if comparison else name
    for row in rows:
        row.setdefault("model_family", "FM")
        row["scientific"] = {"ema": row["ema_momentum"], "peak_learning_rate": row["peak_learning_rate"]}
        row["scientific_hash"] = scientific_row_hash(row)
    row = next(r for r in rows if r["configuration_id"] == configuration_id)
    meta = {"schema_version": "1.0.0", "sequence": CASES.index(name) + 1,
            "phase": "COMPARISON" if comparison else "OFAT", "case": name,
            "configuration_id": configuration_id, "family": row["model_family"],
            "hyperparameters": {k: row[k] for k in ("d", "d_c", "K_aug", "augmentation_intensity", "ema_momentum", "peak_learning_rate")},
            "hyperparameter_basis": "SMOKE_ONLY_COMPARISON_HYPERPARAMETERS" if comparison else "S08_OFAT",
            "seed_namespace": "s09-smoke-only-v1", "seed": smoke_seed(name),
            "rank_seeds": [smoke_seed(name), smoke_seed(name) + 1],
            "formal_authorized": False}
    meta["smoke_config_hash"] = canonical_sha256(meta)
    return matrix, meta


def resolve_inputs() -> dict:
    """Resolve only current configured plan/lineage and content-addressed preparation."""
    import yaml
    from training_campaign import current_lineage, cache_identity, canonical_selection
    from training_prepared_cache import DSRasterCacheReader
    from training_runtime_provenance import runtime_implementation_provenance
    contract = yaml.safe_load((ROOT / "config/training_controller.yml").read_text())
    path = Path(contract["roots"]["experiment_plan"])
    if sha256_file(path) != PLAN_FILE_SHA:
        raise ValueError("SMOKE_CURRENT_S08_BYTES_MISMATCH")
    plan = json.loads(path.read_text())
    if plan["plan_id"] != PLAN_ID or plan["status"] != "PASS":
        raise ValueError("SMOKE_CURRENT_S08_ID_MISMATCH")
    lineage = current_lineage(plan, contract)
    canonical_selection(plan)
    cache = Path(contract["roots"]["production_cache"]) / CACHE_ID
    # The DS reader validates the production acceptance and manifest content hashes
    # even for non-DS cases; it does not load raster payloads at initialization.
    DSRasterCacheReader(cache)
    acceptance = json.loads((cache / "acceptance.json").read_text())
    manifest = json.loads((cache / "production_cache_manifest.json").read_text())
    cache_plan = json.loads((cache / "canonical_cache_plan.json").read_text())
    parents = {**lineage, "cache_implementation_sha256": sha256_file(ROOT / "scripts/prepare_training_cache.py")}
    membership = canonical_sha256(cache_plan["entries"])
    predicted, _ = cache_identity(parents, membership, len(cache_plan["entries"]))
    if (predicted != CACHE_ID or acceptance["acceptance_id"] != ACCEPTANCE_ID
            or manifest["parents"] != parents or manifest["membership_sha256"] != membership
            or len(manifest["entries"]) != 80472):
        raise ValueError("SMOKE_CURRENT_CACHE_LINEAGE_MISMATCH")
    for row in manifest["entries"]:
        payload = cache / "prepared" / f"{row['global_index']:06d}.pt"
        if payload.stat().st_size != row["prepared_size"]:
            raise ValueError("SMOKE_PREPARED_PAYLOAD_INVENTORY_MISMATCH")
    return {"plan": plan, "execution": contract["execution"], "cache_root": str(cache),
            "categories": contract["roots"]["categories"], "lineage": lineage,
            "runtime_sha": runtime_implementation_provenance(ROOT)["implementation_sha256"],
            "input_hashes": {str(p): sha256_file(p) for p in (path, cache / "acceptance.json", cache / "production_cache_manifest.json", cache / "canonical_cache_plan.json")}}


class ProcessGroup:
    """A torchrun session whose descendants are killed on every exit path."""
    def __init__(self, command, **kwargs):
        self.process = subprocess.Popen(command, start_new_session=True, **kwargs)

    def __getattr__(self, name):
        return getattr(self.process, name)

    def terminate_group(self):
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        # The launcher may already have exited while ranks remain alive.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)

    def kill(self):
        self.terminate_group()


@contextmanager
def managed_processes():
    active = []
    def factory(command, **kwargs):
        process = ProcessGroup(command, **kwargs)
        active.append(process)
        return process
    try:
        yield factory
    finally:
        for process in reversed(active):
            process.terminate_group()


@contextmanager
def interrupt_guard():
    def interrupted(signum, frame):
        raise InterruptedError(f"SMOKE_INTERRUPTED_SIGNAL_{signum}")
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def gradient_audit(model) -> dict:
    import torch
    active, frozen = [], []
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            frozen.append(name)
            continue
        if parameter.grad is None or not bool(torch.isfinite(parameter.grad).all()):
            raise ValueError("SMOKE_ACTIVE_GRADIENT_INVALID:" + name)
        active.append(name)
    if not active:
        raise ValueError("SMOKE_NO_ACTIVE_PARAMETERS")
    return {"status": "PASS", "active": active, "nontrainable": frozen, "unexpected_unused": []}


def module_audit(model, family: str) -> dict:
    from model_families import family_contract
    contract = family_contract(family)
    forbidden = []
    if family == "DS":
        forbidden = ["position_encoder", "category_embeddings", "magnitude_encoder", "mask_embeddings"]
    else:
        if "geometry" not in contract.modalities:
            forbidden += ["magnitude_encoder", "phase_encoder", "geometry_fusion"]
        if "semantic" not in contract.modalities:
            forbidden += ["category_embeddings", "poi_embeddings", "poi_projections", "poi_score", "poi_fusion",
                          "building_numerical", "building_fusion", "road_numerical", "road_fusion"]
        retained = set(contract.retained_sources)
        for source, modules in (("B", ("building_numerical", "building_fusion")),
                                ("R", ("road_numerical", "road_fusion")),
                                ("P", ("poi_embeddings", "poi_projections", "poi_score", "poi_fusion"))):
            if source not in retained:
                forbidden.extend(modules)
        categories = getattr(model, "category_embeddings", {})
        for source, names in (("B", ("A9", "A11")), ("R", ("ROAD_RANK", "ROAD_TYPE"))):
            if source not in retained and any(n in categories for n in names):
                raise ValueError("SMOKE_EXCLUDED_SOURCE_MODULE:" + source)
        if "environmental" not in contract.modalities:
            forbidden.append("object_raster_encoder")
        if contract.relation == "none":
            forbidden += ["relation_embedding", "relation_layers"]
        for source, modules in (("LC", ("landcover_embedding", "landcover_cnn", "landcover_projection")),
                                ("DEM", ("dem_cnn", "dem_projection"))):
            if not contract.scene_raster or source not in retained:
                forbidden.extend(modules)
    if any(hasattr(model, name) for name in forbidden):
        raise ValueError("SMOKE_FORBIDDEN_MODULE")
    return {"intentionally_absent": forbidden, "family": family}


@contextmanager
def step_counters(state):
    """Observe method calls without replacing any scientific algorithm."""
    counts = {"optimizer": 0, "scheduler": 0, "ema": 0}
    originals = []
    for obj, method, key in ((state.optimizer, "step", "optimizer"), (state.scheduler, "advance", "scheduler"), (state.model, "update_target", "ema")):
        original = getattr(obj, method)
        def observed(*args, _original=original, _key=key, **kwargs):
            counts[_key] += 1
            return _original(*args, **kwargs)
        originals.append((obj, method, original))
        setattr(obj, method, observed)
    try:
        yield counts
    finally:
        for obj, method, original in originals:
            setattr(obj, method, original)


def assert_step_state(state, counts):
    import torch
    if counts != {"optimizer": 1, "scheduler": 1, "ema": 1} or state.scheduler.completed_updates != 1:
        raise ValueError("SMOKE_NOT_EXACTLY_ONE_STEP")
    if (state.queue["enqueue_count"], state.queue["valid_count"], state.queue["pointer"]) != (64, 64, 64):
        raise ValueError("SMOKE_QUEUE_CONTRACT")
    if any(not bool(torch.isfinite(p).all()) for p in state.model.parameters()):
        raise ValueError("SMOKE_NONFINITE_PARAMETERS")
    if not bool(torch.isfinite(state.queue["values"]).all()):
        raise ValueError("SMOKE_NONFINITE_QUEUE")
    if any(p.requires_grad or p.grad is not None for p in state.model.target.parameters()):
        raise ValueError("SMOKE_TARGET_GRADIENT")


def validation_records(scenes):
    selected = sorted(scenes)[:32]
    if len(selected) != 32 or len(set(selected)) != 32:
        raise ValueError("SMOKE_VALIDATION_POPULATION")
    return [("validation_query", s, 0) for s in selected], [("validation_gallery", s, None) for s in selected]


def validation_smoke(state, values, device):
    import torch
    from training_family_inputs import assemble_family_batch, family_encoder_batch
    from training_support import to_device
    from training_worker import retrieval_rank_diagnostics
    queries, gallery = validation_records(values["data"].validation_scenes)
    state.model.online.eval()
    outputs = []
    try:
        with torch.inference_mode():
            # Keep role batches separate, exactly as the full validation assembler.
            for records in (queries, gallery):
                vectors = []
                for start in range(0, len(records), 8):
                    selected = records[start:start + 8]
                    cpu, geometry, _ = assemble_family_batch(values, selected)
                    ds = values["ds_raster_cache"].batch(cpu, selected[0][0], device) if values["family"] == "DS" else None
                    batch = to_device(family_encoder_batch(cpu), device)
                    geometry = None if geometry is None else tuple(t.to(device) for t in geometry)
                    vector = state.model.online(batch, geometry, ds)["scene_embedding"]
                    vectors.append(torch.nn.functional.normalize(vector, dim=1))
                outputs.append(torch.cat(vectors))
            q, g = outputs
            dimension = int(values["model_config"]["model"]["d"])
            similarities = q @ g.T
            if q.shape != (32, dimension) or g.shape != (32, dimension):
                raise ValueError("SMOKE_VALIDATION_DIMENSION")
            if not all(bool(torch.isfinite(x).all()) for x in (q, g, similarities)):
                raise ValueError("SMOKE_VALIDATION_NONFINITE")
            metrics = retrieval_rank_diagnostics(similarities, torch.arange(32, device=device))
            return {"status": "PASS", "scientific_metric": False, "query_count": 32,
                    "gallery_count": 32, "query_ids": [r[1] for r in queries],
                    "gallery_ids": [r[1] for r in gallery], "output_shape": list(q.shape),
                    "finite": True, "smoke_only_retrieval": metrics}
    finally:
        state.model.online.train()


@contextmanager
def deadline(seconds):
    def expired(signum, frame):
        raise TimeoutError("SMOKE_VALIDATION_TIMEOUT")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def worker(case_file: Path):
    """Only low-level science functions are called; no run_worker/ControllerClient."""
    import resource
    import torch
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel
    import training_worker as science
    from training_runtime_provenance import runtime_implementation_provenance
    from training_transport import validate_formal_transport_environment
    case_file = safe_output(case_file)
    case = json.loads(case_file.read_text())
    directory = case_file.parent
    rank = int(os.environ["LOCAL_RANK"])
    result = {**case["meta"], "runtime_sha": case["runtime_sha"], "rank": rank,
              "device": rank, "world_size": 2, "verdict": "FAIL", "stage": "INITIALIZING"}
    started = time.monotonic()
    try:
        if rank not in (0, 1) or os.environ["WORLD_SIZE"] != "2":
            raise ValueError("SMOKE_WORLD_SIZE")
        validate_formal_transport_environment(os.environ, case["execution"])
        if runtime_implementation_provenance(ROOT)["implementation_sha256"] != case["runtime_sha"]:
            raise ValueError("SMOKE_RUNTIME_CHANGED")
        if tooling_hashes() != case["tooling_hashes"]:
            raise ValueError("SMOKE_TOOLING_CHANGED")
        values = science.load_worker_values(case["spec"])
        values["config"]["training"]["root_seed"] = case["meta"]["seed"]
        device = science.configure_process(values["config"], rank)
        dist.init_process_group("nccl", timeout=dt.timedelta(seconds=60), device_id=device)
        state = science.create_state(values, device)
        result["modules"] = module_audit(state.model.online, values["family"])
        ddp = DistributedDataParallel(state.model.online, device_ids=[rank], output_device=rank,
                                      find_unused_parameters=False, bucket_cap_mb=50,
                                      gradient_as_bucket_view=False, static_graph=False)
        torch.cuda.manual_seed(case["meta"]["seed"] + rank)
        torch.cuda.reset_peak_memory_stats(device)
        result["stage"] = "TRAINING"
        # Capture actual forward input, not a separately reassembled diagnostic batch.
        def capture(module, args):
            batch, geometry, ds, assignment = args
            contract = module.contract
            result.setdefault("views", []).append({
                "entities_B_R_P": [] if values["family"] == "DS" else batch["entities"]["entity_type"].bincount(minlength=3).tolist(),
                "active_modalities": list(contract.modalities),
                "object_environment": list(batch.get("environment", {})),
                "scene_raster": ["DS_ALL_SOURCES"] if ds is not None else list(batch.get("rasters", {})),
                "edge_count": int(batch["edges"]["edge_index"].shape[1]) if "edges" in batch else 0,
                "geometry_rows": 0 if geometry is None else len(geometry[0]),
                "mask_counts_local": None if assignment is None else [(assignment == i).sum().item() for i in range(len(contract.modalities))]})
        hook = state.model.online.register_forward_pre_hook(capture)
        try:
            with step_counters(state) as counts:
                trace = science.training_update(ddp, state, values, 1, 0, rank, device)
            result.update(training=trace, steps=counts, gradients=gradient_audit(state.model.online))
            assert_step_state(state, counts)
        finally:
            hook.remove()
        result["queue"] = {"before": 0, "after": state.queue["valid_count"], "enqueued": state.queue["enqueue_count"]}
        result["stage"] = "VALIDATION"
        with deadline(case["validation_timeout"]):
            result["validation"] = validation_smoke(state, values, device)
        torch.cuda.synchronize()
        result.update(verdict="PASS", stage="COMPLETE", loss_finite=True,
                      peak_allocated_vram=torch.cuda.max_memory_allocated(device),
                      peak_reserved_vram=torch.cuda.max_memory_reserved(device))
    except BaseException:
        result["traceback"] = traceback.format_exc()
        raise
    finally:
        result["wall_seconds"] = time.monotonic() - started
        result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        write_json(directory / f"rank{rank}.json", result)
        if dist.is_initialized():
            dist.destroy_process_group()


def validate_rank_results(ranks, meta, runtime_sha):
    if len(ranks) != 2:
        raise ValueError("SMOKE_RANK_COUNT")
    for index, row in enumerate(ranks):
        if (row.get("rank") != index or row.get("verdict") != "PASS"
                or row.get("runtime_sha") != runtime_sha or row.get("smoke_config_hash") != meta["smoke_config_hash"]
                or row.get("steps") != {"optimizer": 1, "scheduler": 1, "ema": 1}
                or row.get("queue") != {"before": 0, "after": 64, "enqueued": 64}
                or row.get("gradients", {}).get("status") != "PASS"
                or not row.get("gradients", {}).get("active")
                or row.get("gradients", {}).get("unexpected_unused") != []
                or not math.isfinite(row.get("training", {}).get("total_loss", float("nan")))):
            raise ValueError("SMOKE_RANK_RESULT_MISMATCH")
        validation = row.get("validation", {})
        if (validation.get("status") != "PASS" or validation.get("finite") is not True
                or validation.get("query_count") != 32 or validation.get("gallery_count") != 32
                or validation.get("output_shape") != [32, meta["hyperparameters"]["d"]]):
            raise ValueError("SMOKE_VALIDATION_RESULT_MISMATCH")
    if ranks[0]["gradients"]["active"] != ranks[1]["gradients"]["active"]:
        raise ValueError("SMOKE_RANK_PARAMETER_STRUCTURE_MISMATCH")


def run_case(inputs, name: str, directory: Path, case_timeout=240, validation_timeout=60):
    from training_transport import (gpu_pair_environment, run_nccl_transport_preflight,
                                    require_no_conflicting_gpu_workload)
    directory = safe_output(directory)
    directory.mkdir(parents=True, exist_ok=False)
    matrix, meta = case_matrix(inputs["plan"], name)
    write_json(directory / "inputs.json", matrix)
    case = {"meta": meta, "runtime_sha": inputs["runtime_sha"], "execution": inputs["execution"],
            "tooling_hashes": tooling_hashes(),
            "validation_timeout": validation_timeout,
            "spec": {"matrix": str(directory / "inputs.json"), "configuration_id": meta["configuration_id"],
                     "cache_root": inputs["cache_root"], "categories": inputs["categories"],
                     "training_config": str(ROOT / "config/training.yml"), "model_config": str(ROOT / "config/model_inputs.yml")}}
    write_json(directory / "case.json", case)
    result = {**meta, "runtime_sha": inputs["runtime_sha"], "verdict": "FAIL", "stage": "PREFLIGHT"}
    started = time.monotonic()
    try:
        require_no_conflicting_gpu_workload()
        with gpu_pair_environment(inputs["execution"]) as env, managed_processes() as factory:
            for key in tuple(env):
                if key.startswith("FUSE_TRAINING_"):
                    del env[key]
            env.update(PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
            require_no_conflicting_gpu_workload()
            with safe_output(directory / "preflight.jsonl").open("x") as log:
                log.write(json.dumps({"status": "STARTED", "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "case": name}) + "\n"); log.flush()
                try:
                    result["preflight"] = run_nccl_transport_preflight(ROOT, inputs["execution"], env, popen_factory=factory)
                    log.write(json.dumps(result["preflight"]) + "\n")
                except BaseException:
                    log.write(json.dumps({"status": "FAIL", "traceback": traceback.format_exc()}) + "\n")
                    raise
            result["stage"] = "WORKER"
            command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
                       "--log-dir", str(directory / "ranks"), "--redirects", "3",
                       str(ROOT / "scripts/s09_smoke_matrix.py"), "--worker-case", str(directory / "case.json")]
            with safe_output(directory / "stdout.log").open("x") as stdout, safe_output(directory / "stderr.log").open("x") as stderr:
                process = factory(command, env=env, stdout=stdout, stderr=stderr)
                if process.wait(timeout=case_timeout) != 0:
                    raise RuntimeError("SMOKE_RANK_FAILED")
            ranks = [json.loads((directory / f"rank{r}.json").read_text()) for r in (0, 1)]
            validate_rank_results(ranks, meta, inputs["runtime_sha"])
            result.update(verdict="PASS", stage="COMPLETE", ranks=ranks)
    except BaseException:
        result["traceback"] = traceback.format_exc()
        raise
    finally:
        result["wall_seconds"] = time.monotonic() - started
        write_json(directory / "case_result.json", result)
    return result


def run_matrix(names, output=None):
    if not names or any(name not in CASES for name in names) or len(set(names)) != len(names):
        raise ValueError("INVALID_SMOKE_SELECTION")
    names = [name for name in CASES if name in names]
    output = safe_output(output or SMOKE_ROOT / dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f"))
    output.mkdir(parents=True, exist_ok=False)
    try:
        inputs = resolve_inputs()
    except BaseException:
        write_json(output / "input_failure.json", {"verdict": "FAIL", "traceback": traceback.format_exc()})
        raise
    write_json(output / "matrix.json", {"case_order": list(CASES), "selected": names,
                "runtime_sha": inputs["runtime_sha"], "tooling_hashes": tooling_hashes(),
                "input_hashes": inputs["input_hashes"], "formal_authorized": False})
    with interrupt_guard(), safe_output(output / "matrix.tsv").open("x") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(("sequence", "phase", "case", "verdict", "wall_seconds")); stream.flush()
        for name in names:
            try:
                result = run_case(inputs, name, output / name)
            except BaseException:
                writer.writerow((CASES.index(name) + 1, "OFAT" if name in OFAT else "COMPARISON", name, "FAIL", "NA")); stream.flush()
                raise
            writer.writerow((result["sequence"], result["phase"], name, result["verdict"], result["wall_seconds"])); stream.flush()
    if any(sha256_file(path) != digest for path, digest in inputs["input_hashes"].items()):
        raise ValueError("SMOKE_PROTECTED_INPUT_MUTATION")
    return output
