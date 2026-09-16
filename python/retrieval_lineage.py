"""Read-only S09 acceptance resolution and accepted original-scene lineage for S10."""
from pathlib import Path
import json
import hashlib
import platform
import importlib.metadata
import ast
import yaml
import pyarrow.parquet as pq

from artifact_protocol import canonical_sha256
from retrieval_artifacts import require, read_json, file_hash, digest
from retrieval_ranking import OFAT, COMPARISON

ROOT = Path(__file__).resolve().parents[1]


def config(path):
    import jsonschema
    value = yaml.safe_load(Path(path).read_text())
    jsonschema.validate(value, read_json(ROOT / "config/schemas/retrieval_visualization.schema.json"))
    for p, checksum in value["source_pins"].items():
        require(file_hash(p) == checksum, "SCIENTIFIC_SOURCE_PIN:" + p)
    return value


def runtime(cfg):
    # Bind the local import closure, explicitly excluding the unrelated S11 lifecycle.
    pending = [p.stem for p in ROOT.glob("python/retrieval_*.py")]
    paths, seen = [], set()
    while pending:
        name = pending.pop()
        p = ROOT / "python" / (name + ".py")
        if name in seen or not p.is_file(): continue
        seen.add(name)
        paths.append(p)
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                pending.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                pending.extend(n.name.split(".")[0] for n in node.names)
    require(not ({"evaluation", "evaluation_inputs"} & seen), "S11_RUNTIME_DEPENDENCY")
    paths = sorted([*paths, *ROOT.glob("tools/retrieval_inspector/*"),
        ROOT / "config/retrieval_visualization.yml", ROOT / "config/model_inputs.yml",
        ROOT / "scripts/retrieval_visualization.py", ROOT / "R/retrieval_visualization.R",
        ROOT / "targets/s10_retrieval_visualization.R", ROOT / "_targets_retrieval_visualization.R",
        *ROOT.glob("config/schemas/retrieval*.json")])
    sources = {str(p.relative_to(ROOT)): file_hash(p) for p in paths if p.is_file()}
    versions = {p: importlib.metadata.version(p) for p in ("torch", "numpy", "pyarrow", "shapely", "zarr", "triangle")}
    value = {"sources": sources, "versions": versions, "python": platform.python_version(),
             "device": cfg["device"], "threads": cfg["threads"], "batch_size": cfg["batch_size"],
             "inference_seed": cfg["inference_seed"], "deterministic_algorithms": True,
             "tf32": False, "cublas_workspace_config": ":4096:8"}
    import torch
    value["default_dtype"] = str(torch.get_default_dtype())
    value["cudnn_version"] = torch.backends.cudnn.version()
    value["cuda_version"] = torch.version.cuda
    if cfg["device"].startswith("cuda:"):
        props = torch.cuda.get_device_properties(torch.device(cfg["device"]))
        value["gpu"] = {"name": props.name, "capability": [props.major, props.minor],
                        "total_memory": props.total_memory, "uuid": str(props.uuid)}
    return {**value, "runtime_id": digest(value)}


def inventory(cfg):
    """Follow campaign -> winner/results -> native acceptance -> committed bundle."""
    from training_acceptance import resolve_accepted_checkpoint
    from training_controller import validate_training_authority
    from training_runtime_provenance import runtime_implementation_provenance
    path = Path(cfg["campaign"])
    require(file_hash(path) == cfg["campaign_sha256"], "CAMPAIGN_PIN")
    c = read_json(path)
    require(c["status"] == "PASS" and c["training_runs"] == 28 and c["evaluation_runs"] == 0,
            "CAMPAIGN_NOT_ACCEPTED")
    require(c["campaign_acceptance_id"] == cfg["campaign_id"], "CAMPAIGN_ID")
    # S09 campaign uses insertion-ordered jsonlite JSON, not the sorted native encoding.
    preimage = {k: v for k, v in c.items() if k not in ("content_sha256", "campaign_acceptance_id")}
    require(hashlib.sha256(json.dumps(preimage, separators=(",", ":")).encode()).hexdigest() == c["content_sha256"], "CAMPAIGN_HASH")
    require(c["campaign_acceptance_id"] == "s09camp_" + c["content_sha256"][:24], "CAMPAIGN_CONTENT_ID")
    require(runtime_implementation_provenance(ROOT)["implementation_sha256"] == c["runtime_implementation_sha256"], "S09_RUNTIME_CHANGED")
    winner_path = path.parent.parent / c["experiment_plan_id"] / c["runtime_implementation_sha256"] / "ofat_winner.json"
    winner = read_json(winner_path)
    require(winner["winner_id"] == c["winner_id"] and winner["status"] == "PASS", "WINNER_BINDING")
    require(canonical_sha256({k: v for k, v in winner.items() if k not in ("winner_id", "content_sha256")}) == winner["content_sha256"], "WINNER_HASH")
    require(winner["winner_id"] == "s09winner_" + winner["content_sha256"][:24], "WINNER_CONTENT_ID")
    rows = winner["candidate_results"] + [read_json(p) for p in c["comparison_acceptance_records"]]
    expected = list(OFAT) + ["cmp_" + m for m in COMPARISON]
    require(len(rows) == 28 and [r["configuration_id"] for r in rows] == expected, "MODEL_INVENTORY")
    control = yaml.safe_load(Path(cfg["training_controller"]).read_text())
    canonical = Path(control["roots"]["canonical_publication"])
    results = []
    evidence = {str(path): file_hash(path), str(winner_path): file_hash(winner_path)}
    for row in rows:
        require(row["status"] == "PASS", "MODEL_RESULT_MISSING")
        handoff = read_json(row["acceptance_record"])
        resolved = resolve_accepted_checkpoint(handoff["acceptance_id"], canonical / "acceptances",
            canonical / "bundles", {handoff["checkpoint_namespace"]: handoff["checkpoint_root"]})
        bundle = canonical / "bundles" / resolved.run_bundle_id
        auth_path = bundle / "authority/authority_manifest.json"
        auth = read_json(auth_path)
        validate_training_authority(auth)
        require(resolved.checkpoint_id == row["checkpoint_id"] and resolved.authority_id == row["authority_id"] == auth["identity"], "CHECKPOINT_LINEAGE")
        science = auth["content"]["scientific"]
        require(science["configuration_id"] == row["configuration_id"] and science["model_id"] == row["model_id"], "MODEL_IDENTITY")
        require(science["scientific_implementation_hash"] == c["runtime_implementation_sha256"], "STALE_CHECKPOINT")
        parents = auth["content"]["parents"]
        if row["phase"] == "COMPARISON":
            require(parents["ofat_winner_id"] == winner["winner_id"], "COMPARISON_WINNER_BINDING")
        require(parents["production_cache_acceptance_id"] == c["prepared_cache_acceptance_id"] and
                parents["experiment_plan_id"] == c["experiment_plan_id"], "PARENT_BINDING")
        for key, value in control["parents"].items():
            require(parents[key] == value, "TRAINING_PARENT:" + key)
        loc = resolved.payload_locator["location"]
        require(loc["namespace"] == handoff["checkpoint_namespace"], "CHECKPOINT_NAMESPACE")
        payload = (Path(handoff["checkpoint_root"]) / loc["relative_path"]).resolve()
        require(payload.is_relative_to(Path(handoff["checkpoint_root"]).resolve()), "CHECKPOINT_PATH")
        require(file_hash(payload) == resolved.payload_sha256, "CHECKPOINT_BYTES")
        for p in (Path(row["acceptance_record"]), auth_path, bundle / "config/scientific_configuration.json"):
            evidence[str(p)] = file_hash(p)
        results.append({"configuration_id": row["configuration_id"], "model_id": row["model_id"],
            "group": row["phase"], "checkpoint_id": resolved.checkpoint_id,
            "acceptance_id": resolved.acceptance_id, "bundle_id": resolved.run_bundle_id,
            "authority_id": resolved.authority_id, "payload": str(payload),
            "payload_sha256": resolved.payload_sha256, "manifest_sha256": resolved.manifest_sha256,
            "scientific_configuration": resolved.scientific_configuration})
    return {"models": results, "campaign_id": c["campaign_acceptance_id"],
            "s09_runtime": c["runtime_implementation_sha256"], "parents": parents,
            "evidence": evidence, "roots": control["roots"]}


class OriginalCatalog:
    """Only accepted P3 originals, no augmented query/evaluation lifecycle imports."""
    def __init__(self, roots, training, parent_hashes=None):
        self.root = Path(roots["p3"])
        parents = training["parents"]
        acceptance_path = self.root / "acceptance" / parents["p3_acceptance_id"] / "original_scene_dataset_acceptance.json"
        acceptance = read_json(acceptance_path)
        require(acceptance["status"] == "PASS" and acceptance["cache_id"] == parents["p3_cache_id"] and
                acceptance["acceptance_id"] == parents["p3_acceptance_id"], "P3_ACCEPTANCE")
        paths = list((self.root / "index").glob("*/scene_to_shard.parquet"))
        require(len(paths) == 1, "P3_INDEX_AMBIGUOUS")
        self.index_path = paths[0]
        rows = pq.read_table(paths[0]).to_pylist()
        self.p3_by_scene = {r["scene_id"]: r for r in rows}
        require(len(rows) == len(self.p3_by_scene) == 12421 and
                all(r["cache_id"] == parents["p3_cache_id"] for r in rows), "P3_MEMBERSHIP")
        self.verified = set()

    def p3_tar(self, scene_id):
        row = self.p3_by_scene[scene_id]
        path = self.root / "shards" / row["branch_id"] / row["payload_filename"]
        if path not in self.verified:
            require(file_hash(path) == row["payload_sha256"], "P3_PAYLOAD")
            self.verified.add(path)
        return path, row


def population(cfg, model_body):
    from training_runtime_inputs import SceneCenterIndex
    training = yaml.safe_load(Path(cfg["training_config"]).read_text())
    roots = model_body["roots"]
    parents = model_body["parents"]
    preprocessing = read_json(roots["preprocessing"])
    require(preprocessing["status"] == "PASS" and preprocessing["fit_split"] == "training" and
            preprocessing["p3_cache_id"] == parents["scene_cache_id"] and
            preprocessing["preprocessing_id"] == training["parents"]["p6_preprocessing_id"], "PREPROCESSING_LINEAGE")
    centers = SceneCenterIndex.from_current_contract(training,
        Path(roots["production_cache"]) / parents["production_cache_id"])
    catalog = OriginalCatalog(roots, training)
    rows = []
    for scene, (x, y, split) in sorted(centers.centers.items()):
        if split == "evaluation":
            r = catalog.p3_by_scene[scene]
            # P3 index records membership/payload only. Accepted P1 carries split;
            # original payload split is checked again before each inference.
            rows.append({"scene_id": scene, "center_x": x, "center_y": y,
                         "split": split, "epsg": 5186, "source_payload_sha256": r["payload_sha256"]})
    require(len(rows) == 9000, "EVALUATION_POPULATION")
    return rows, {"scene_index_id": centers.scene_index_id,
        "scene_acceptance_id": centers.scene_acceptance_id, "p3_index_sha256": file_hash(catalog.index_path),
        "p3_cache_id": centers.p3_cache_id}
