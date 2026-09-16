"""S10 deterministic originals-only inference; no optimizer or training entrypoint.

Uses S09 family projection and the dissertation scene embedding (not projection head).
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import os
import random
import numpy as np
import torch
import yaml

from retrieval_artifacts import require, file_hash, read_json, load
from retrieval_lineage import OriginalCatalog
from model_data import read_original_scene, tensorize_scene, build_vocabulary, validate_vocabulary_contract
from model_families import build_scene_encoder, family_contract, ds_raster_from_batch
from training_family_inputs import project, projected_collate, family_encoder_batch, project_fourier
from training_configuration import materialize_hyperparameter_configuration
from training_support import collate, to_device
from scene_model import geometry_fourier_features


@contextmanager
def device_lock(cfg):
    if not cfg["device"].startswith("cuda:"):
        yield
        return
    index = int(cfg["device"].split(":")[1])
    root = Path(cfg["gpu_lock_root"])
    root.mkdir(parents=True, exist_ok=True)
    with (root / f"gpu{index}.lock").open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def initialize_inference(cfg):
    require(cfg["batch_size"] == 1, "BATCH_ONE_REQUIRED")
    require(torch.get_default_dtype() == torch.float32, "DEFAULT_FLOAT32_REQUIRED")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    random.seed(cfg["inference_seed"])
    np.random.seed(cfg["inference_seed"])
    torch.manual_seed(cfg["inference_seed"])
    torch.set_num_threads(cfg["threads"])
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    return torch.device(cfg["device"])


def infer(cfg, model_record, roots, gallery, prepared_path=None, precomputed_geometry_features=None):
    device = initialize_inference(cfg)
    training = yaml.safe_load(Path(cfg["training_config"]).read_text())
    base_model = yaml.safe_load(Path(cfg["model_config"]).read_text())
    scientific = model_record["scientific_configuration"]
    routed = materialize_hyperparameter_configuration(scientific["content"], training, base_model)
    vocabulary = build_vocabulary(roots["categories"])
    preprocessing = read_json(roots["preprocessing"])
    catalog = OriginalCatalog(roots, training) if prepared_path is None else None
    prepared = load(prepared_path, "original_inputs") if prepared_path else None
    prepared_rows = {r["scene_id"]: r for r in prepared["body"]["samples"]} if prepared else {}
    family = model_record["model_id"]
    contract = family_contract(family)
    geometry_reader = None
    if "geometry" in contract.modalities and precomputed_geometry_features is not None:
        from retrieval_geometry import GeometryReader
        require(prepared is not None, "GEOMETRY_PREPARED_REQUIRED")
        geometry_reader = GeometryReader(precomputed_geometry_features, prepared,
                                         routed["model"]["model"]["geometry"], cfg)
    require(file_hash(model_record["payload"]) == model_record["payload_sha256"], "CHECKPOINT_MUTATED")
    with device_lock(cfg):
        payload = torch.load(model_record["payload"], map_location="cpu", weights_only=False)
        require(payload["configuration_identity"] == scientific["content_sha256"], "CHECKPOINT_CONFIGURATION")
        model = build_scene_encoder(routed["model"], validate_vocabulary_contract(vocabulary), family).to(device)
        model.load_state_dict(payload["online_model"], strict=True)
        del payload
        model.eval()
        model.requires_grad_(False)
        vectors = []
        with torch.inference_mode():
            for start in range(0, len(gallery), cfg["batch_size"]):
                projected, fourier = [], []
                for row in gallery[start:start + cfg["batch_size"]]:
                    if prepared is not None:
                        sample = torch.load(Path(prepared_path).parent / prepared_rows[row["scene_id"]]["path"],
                                            map_location="cpu", weights_only=False)
                        require(sample["scene_id"] == row["scene_id"] and
                                np.array_equal(sample["scene_center_5186"].numpy(), [row["center_x"],row["center_y"]]), "PREPARED_SCENE_BINDING")
                    else:
                        scene = read_original_scene(catalog, row["scene_id"])
                        require(scene["split"] == "evaluation" and np.array_equal(scene["center"], [row["center_x"], row["center_y"]]), "SCENE_CENTER_BINDING")
                        sample = tensorize_scene(scene, preprocessing, vocabulary)
                        sample["scene_center_5186"] = torch.tensor(scene["center"], dtype=torch.float64)
                    projected_sample, metadata = project(sample, family)
                    if "geometry" in contract.modalities:
                        raw = (geometry_reader.get(sample) if geometry_reader is not None else
                               geometry_fourier_features(collate([sample], vocabulary),
                                   {"geometry": routed["model"]["model"]["geometry"]}, device))
                        fourier.append(project_fourier(tuple(x.cpu() for x in raw), metadata,
                                                       projected_sample["entities"]["local_entity_id"]))
                    projected.append((projected_sample, metadata))
                cpu = projected_collate(projected, vocabulary)
                cpu["family_name"] = family
                env, offset, blocks = cpu["entities"]["object_raster"], 0, {}
                for source, width in (("LC", 23), ("DEM", 3)):
                    if "environmental" in contract.modalities and source in contract.retained_sources:
                        blocks[source] = env[:, offset:offset + width]
                        offset += width
                require(offset == env.shape[1], "FAMILY_ENVIRONMENT")
                cpu["environment"] = blocks
                ds = ds_raster_from_batch(cpu).to(device) if family == "DS" else None
                geometry = tuple(torch.cat([r[i] for r in fourier]).to(device) for i in (0, 1)) if fourier else None
                batch = to_device(family_encoder_batch(cpu), device)
                output = model(batch, geometry, ds)["scene_embedding"]
                require(bool(torch.isfinite(output).all()) and bool((output.norm(dim=1) > 0).all()), "INVALID_RAW_EMBEDDING")
                vectors.append(torch.nn.functional.normalize(output, dim=1).cpu().numpy())
        del model
    require(file_hash(model_record["payload"]) == model_record["payload_sha256"], "CHECKPOINT_MUTATED")
    return np.concatenate(vectors)
