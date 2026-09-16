"""S10 common pre-MLP Fourier features (dissertation eq:mag-phase).

Calls the unchanged accepted GPU function on one original scene at a time.
No checkpoint, learned projection, relation layer, training or S11 lifecycle.
"""
from pathlib import Path
import io
import hashlib
import torch
import yaml

from retrieval_artifacts import require, digest, file_hash, load, publish, publish_bytes, read_json
from model_data import build_vocabulary, GEOMETRY_LAYOUT_VERSION
from model_families import family_contract
from training_configuration import materialize_hyperparameter_configuration
from training_support import collate
from scene_model import geometry_fourier_features

SCHEMA = "s10-fourier-v1"
ROOT = Path(__file__).resolve().parents[1]


def active(model):
    return "geometry" in family_contract(model["model_id"]).modalities


def implementation_identity():
    names = ("scene_encoder.py", "scene_model.py", "model_data.py", "training_support.py",
             "training_family_inputs.py", "retrieval_geometry.py")
    sources = {"python/" + n: file_hash(ROOT / "python" / n) for n in names}
    return {"sources": sources, "sha256": digest(sources), "function": "scene_encoder.geometry_fourier_features",
            "implementation": "vectorized"}


def configuration_groups(cfg, models):
    training = yaml.safe_load(Path(cfg["training_config"]).read_text())
    base = yaml.safe_load(Path(cfg["model_config"]).read_text())
    groups = {}
    for model in models:
        if not active(model):
            continue
        routed = materialize_hyperparameter_configuration(model["scientific_configuration"]["content"], training, base)
        geometry = routed["model"]["model"]["geometry"]
        key = digest(geometry)
        if key not in groups:
            groups[key] = {"configuration": geometry, "configuration_sha256": key, "models": []}
        groups[key]["models"].append(model["configuration_id"])
    return [groups[k] for k in sorted(groups)]


def tensor_hash(value):
    return hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def source_record(sample, file_record, original, configuration, implementation):
    require(sample["split"] == "evaluation" and sample["view_id"] == "original" and sample["profile"] is None,
            "GEOMETRY_ORIGINAL_ONLY")
    require(sample["geometry"]["part_coordinates_xy_m"].dtype == torch.float32 and
            sample["geometry"]["ring_coordinates_xy_m"].dtype == torch.float32, "GEOMETRY_INPUT_DTYPE")
    order = torch.stack((sample["entities"]["local_entity_id"], sample["entities"]["entity_type"]), dim=1)
    width = int(configuration["radial_frequencies"]) * int(configuration["angular_orientations"])
    identity = {"schema": SCHEMA, "scene_id": sample["scene_id"],
        "original_manifest_id": original["artifact_id"], "original_payload_sha256": file_record["sha256"],
        "preprocessing_id": original["body"]["preprocessing_id"],
        "preprocessing_sha256": original["body"]["preprocessing_sha256"],
        "categories_sha256": original["body"]["categories_sha256"],
        "geometry_configuration_sha256": digest(configuration), "implementation_sha256": implementation["sha256"],
        "runtime_id": original["body"]["runtime_id"], "generation_id": original["body"]["generation_id"],
        "geometry_layout_version": GEOMETRY_LAYOUT_VERSION, "entity_order_sha256": tensor_hash(order),
        "dtype": "torch.float32", "shapes": [[len(order), width], [len(order), 2 * width]]}
    return {**identity, "cache_key": digest(identity)}


def validate_features(values, record):
    require(isinstance(values, (tuple, list)) and len(values) == 2, "GEOMETRY_TENSORS")
    for value, shape in zip(values, record["shapes"], strict=True):
        require(isinstance(value, torch.Tensor) and value.device.type == "cpu" and
                value.dtype == torch.float32 and list(value.shape) == shape and
                bool(torch.isfinite(value).all()), "GEOMETRY_TENSOR_CONTRACT")
    return tuple(values)


def create_cache(cfg, models, roots, original_path, output):
    """Bounded shard writer; callers enforce formal execution authorization."""
    from retrieval_inference import initialize_inference, device_lock
    require(cfg["device"].startswith("cuda:") and cfg["batch_size"] == 1, "GEOMETRY_GPU_BATCH_ONE")
    original = load(original_path, "original_inputs")
    rows = original["body"]["samples"]
    ids = [r["scene_id"] for r in rows]
    require(ids == sorted(set(ids)) and len(ids) == cfg["gallery_count"], "GEOMETRY_SCENE_ORDER")
    if original["body"]["scope"] == "formal":
        import os
        require(os.environ.get("FUSE_S10_FULL_AUTHORIZED") == "1", "FULL_GEOMETRY_NOT_AUTHORIZED")
    else:
        require(len(ids) <= 100 and not Path(output).resolve().is_relative_to(Path(cfg["publication_root"]).resolve()),
                "GEOMETRY_BOUNDED_SCOPE")
    groups = configuration_groups(cfg, models)
    require(bool(groups), "GEOMETRY_NO_ACTIVE_MODELS")
    implementation = implementation_identity()
    file_records = {r["path"]: r for r in original["files"]}
    vocabulary = build_vocabulary(roots["categories"])
    require(file_hash(roots["categories"]) == original["body"]["categories_sha256"] and
            file_hash(roots["preprocessing"]) == original["body"]["preprocessing_sha256"], "GEOMETRY_SOURCE_BINDING")
    preprocessing = read_json(roots["preprocessing"])
    require(preprocessing["preprocessing_id"] == original["body"]["preprocessing_id"], "GEOMETRY_PREPROCESSING_ID")
    device = initialize_inference(cfg)
    output = Path(output)
    files, published_groups = [], []
    shard_size = cfg.get("geometry_cache_scenes_per_shard", 100)
    require(shard_size == 100, "GEOMETRY_STORAGE_CONTRACT")
    with device_lock(cfg), torch.inference_mode():
        for group in groups:
            entries, shard = [], []
            for index, row in enumerate(rows):
                sample = torch.load(Path(original_path).parent / row["path"], map_location="cpu", weights_only=False)
                require(sample["scene_id"] == row["scene_id"], "GEOMETRY_SCENE_BINDING")
                record = source_record(sample, file_records[row["path"]], original, group["configuration"], implementation)
                raw = geometry_fourier_features(collate([sample], vocabulary), {"geometry": group["configuration"]}, device)
                values = validate_features(tuple(x.cpu().contiguous() for x in raw), record)
                shard_name = f'{group["configuration_sha256"]}/{index // shard_size:06d}.pt'
                entry = {"record": record, "features": values}
                shard.append(entry)
                entries.append({"scene_id": row["scene_id"], "record": record, "path": shard_name,
                                "position": index % shard_size, "tensor_sha256": [tensor_hash(x) for x in values]})
                if len(shard) == shard_size or index + 1 == len(rows):
                    buffer = io.BytesIO()
                    torch.save(shard, buffer)
                    files.append(publish_bytes(output / shard_name, buffer.getvalue()))
                    shard = []
            published_groups.append({**group, "entries": entries})
    ctx = {k: original["body"][k] for k in ("generation_id", "runtime_id", "scope", "model_manifest_id",
                                           "query_manifest_id", "gallery_manifest_id")}
    return publish(output / "manifest.json", "geometry_features", {**ctx, "schema": SCHEMA,
        "original_manifest_id": original["artifact_id"], "preprocessing_id": preprocessing["preprocessing_id"],
        "preprocessing_sha256": original["body"]["preprocessing_sha256"],
        "categories_sha256": original["body"]["categories_sha256"], "implementation": implementation,
        "scene_count": len(ids), "scene_ids": ids, "groups": published_groups,
        "storage": {"format": "torch-shards", "scenes_per_shard": shard_size},
        "creation": {"generator": "S10 common original GPU Fourier", "device": cfg["device"],
                     "seed": cfg["inference_seed"], "dtype": "torch.float32", "default_dtype": str(torch.get_default_dtype()),
                     "batch_size": 1, "deterministic_algorithms": True, "tf32": False}}, files)


class GeometryReader:
    """Verify the whole immutable cache; retain at most one shard during inference."""
    def __init__(self, path, original, configuration, cfg):
        self.path = Path(path)
        self.manifest = load(path, "geometry_features")
        body = self.manifest["body"]
        require(body["schema"] == SCHEMA and body["original_manifest_id"] == original["artifact_id"], "GEOMETRY_ORIGINAL_BINDING")
        for key in ("generation_id", "runtime_id", "scope", "model_manifest_id", "query_manifest_id", "gallery_manifest_id",
                    "preprocessing_id", "preprocessing_sha256", "categories_sha256"):
            require(body[key] == original["body"][key], "GEOMETRY_SOURCE_BINDING:" + key)
        require(body["implementation"] == implementation_identity(), "GEOMETRY_IMPLEMENTATION")
        require(body["creation"]["device"] == cfg["device"] and body["creation"]["seed"] == cfg["inference_seed"] and
                body["creation"]["dtype"] == body["creation"]["default_dtype"] == "torch.float32" and
                body["creation"]["batch_size"] == cfg["batch_size"] == 1 and
                body["creation"]["deterministic_algorithms"] is True and body["creation"]["tf32"] is False,
                "GEOMETRY_RUNTIME")
        require(body["storage"] == {"format": "torch-shards", "scenes_per_shard": 100}, "GEOMETRY_STORAGE_CONTRACT")
        ids = [r["scene_id"] for r in original["body"]["samples"]]
        require(ids == sorted(set(ids)) and body["scene_ids"] == ids and body["scene_count"] == len(ids), "GEOMETRY_SCENE_ORDER")
        keys = [g["configuration_sha256"] for g in body["groups"]]
        require(keys == sorted(set(keys)), "GEOMETRY_GROUP_ORDER")
        key = digest(configuration)
        require(key in keys, "GEOMETRY_CONFIG")
        group = body["groups"][keys.index(key)]
        require(group["configuration"] == configuration and [r["scene_id"] for r in group["entries"]] == ids, "GEOMETRY_MISSING_SCENE")
        self.entries = {r["scene_id"]: r for r in group["entries"]}
        self.files = {r["path"]: r for r in self.manifest["files"]}
        require(len(self.files) == len(self.manifest["files"]), "GEOMETRY_DUPLICATE_FILE")
        for i, entry in enumerate(group["entries"]):
            require(entry["path"] == f'{key}/{i // 100:06d}.pt' and entry["position"] == i % 100 and
                    entry["path"] in self.files, "GEOMETRY_SHARD_INDEX")
        self.original, self.configuration = original, configuration
        self.original_files = {r["path"]: r for r in original["files"]}
        self.original_rows = {r["scene_id"]: r for r in original["body"]["samples"]}
        self.shard_path, self.shard = None, None

    def get(self, sample):
        sid = sample["scene_id"]
        require(sid in self.entries, "GEOMETRY_MISSING_SCENE")
        entry = self.entries[sid]
        expected = source_record(sample, self.original_files[self.original_rows[sid]["path"]], self.original,
                                 self.configuration, self.manifest["body"]["implementation"])
        require(entry["record"] == expected, "GEOMETRY_ENTITY_SOURCE_BINDING")
        if self.shard_path != entry["path"]:
            path = self.path.parent / entry["path"]
            require(file_hash(path) == self.files[entry["path"]]["sha256"], "GEOMETRY_PAYLOAD")
            self.shard = torch.load(path, map_location="cpu", weights_only=False)
            require(isinstance(self.shard, list) and 1 <= len(self.shard) <= 100, "GEOMETRY_SHARD")
            self.shard_path = entry["path"]
        require(entry["position"] < len(self.shard), "GEOMETRY_MISSING_FEATURE")
        value = self.shard[entry["position"]]
        require(value["record"] == expected, "GEOMETRY_PAYLOAD_BINDING")
        values = validate_features(value["features"], expected)
        require([tensor_hash(x) for x in values] == entry["tensor_sha256"], "GEOMETRY_FEATURE_HASH")
        return values
