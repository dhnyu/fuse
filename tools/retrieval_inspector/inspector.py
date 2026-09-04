"""Build a deterministic browser inspector from immutable P3/P10 evidence.

This module never runs an encoder. It reconstructs qualitative rankings from the
accepted P10 original-gallery embeddings and renders accepted P3 scene payloads.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import tarfile
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pyarrow.parquet as pq
import shapely
import yaml
import zarr

from p10_evaluation import (
    MODEL_IDS, _qualitative, evaluation_population, load_contract,
    make_qualitative_contract, resolve_model_bindings,
)
from p10_prepared_input import P10PreparedInputCache
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file


SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "retrieval-inspector-v1"
P10_ACCEPTANCE_ID = "p10acc_6e5071beee7616750dec7907"
P10_ATTEMPT_ID = "p10exec_7fee193dac532190c79e02c6"
P10_QUERY_CONTRACT_ID = "p10qq_dd7d0775f5809a793575342b"
MODEL_LABELS = {
    "cfg_d128": "cfg_d128",
    "cmp_a1_geometric_core": "A1",
    "cmp_a2_semantic_enriched": "A2",
    "cmp_a3_object_context_enriched": "A3",
    "cmp_a4_raster_complete_non_relational": "A4",
    "cmp_a5_relation_type_agnostic": "A5",
    "cmp_ssv_like": "SSV",
    "cmp_ds_like": "DS",
}
LC_COLORS = (
    "#d9d9d9", "#ef476f", "#f78c6b", "#ffd166", "#c7d36f", "#80b918",
    "#55a630", "#2b9348", "#168aad", "#1a759f", "#184e77", "#6c757d",
    "#adb5bd", "#9b5de5", "#f15bb5", "#fee440", "#00bbf9", "#00f5d4",
    "#bc6c25", "#dda15e", "#606c38", "#283618",
)


class InspectorError(RuntimeError):
    """A fail-closed source, ranking, or publication error."""


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InspectorError(f"JSON object required: {path}")
    return value


def _canonical(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def band_ranks(candidate_count: int) -> dict[str, list[int]]:
    """Return non-overlapping one-based rank bands for a ranking of length N."""
    if candidate_count < 31:
        raise InspectorError("at least 31 candidates are required")
    middle_start = (candidate_count - 10) // 2 + 1
    result = {
        "most": [1],
        "top": list(range(2, 12)),
        "middle": list(range(middle_start, middle_start + 10)),
        "bottom": list(range(candidate_count - 9, candidate_count + 1)),
    }
    flattened = [rank for values in result.values() for rank in values]
    if len(flattened) != 31 or len(set(flattened)) != 31:
        raise InspectorError("rank bands overlap")
    return result


def _rle(values: Iterable[int | float | None]) -> list[list[int | float | None]]:
    output: list[list[int | float | None]] = []
    for value in values:
        if value is None:
            item: int | float | None = None
        elif isinstance(value, (int, np.integer)):
            item = int(value)
        else:
            item = float(value)
        if output and output[-1][0] == item:
            output[-1][1] = int(output[-1][1]) + 1
        else:
            output.append([item, 1])
    return output


def _geometry(geometry: Any, xmin: float, ymin: float) -> dict[str, Any]:
    mapping = shapely.geometry.mapping(geometry)

    def coordinates(value: Any) -> Any:
        if value and isinstance(value[0], (int, float)):
            return [round(float(value[0]) - xmin, 6), round(float(value[1]) - ymin, 6)]
        return [coordinates(item) for item in value]

    return {"type": mapping["type"], "coordinates": coordinates(mapping["coordinates"])}


def _counter(rows: Sequence[Mapping[str, Any]], key: str, limit: int = 8) -> list[dict[str, Any]]:
    values = Counter(str(row.get(key) or "Unavailable") for row in rows)
    return [{"label": label, "count": count} for label, count in values.most_common(limit)]


def _table(archive: tarfile.TarFile, name: str) -> list[dict[str, Any]]:
    member = archive.extractfile(name)
    if member is None:
        raise InspectorError(f"missing P3 member: {name}")
    return pq.read_table(io.BytesIO(member.read())).to_pylist()


def _extract_zarr(archive: tarfile.TarFile, destination: Path) -> None:
    prefixes = ("raster/scene_landcover.zarr/", "raster/scene_dem.zarr/")
    members = [member for member in archive.getmembers() if member.name.startswith(prefixes)]
    root = destination.resolve()
    for member in members:
        target = (destination / member.name).resolve()
        if root not in target.parents:
            raise InspectorError(f"archive path escape: {member.name}")
    archive.extractall(destination, members=members, filter="data")


def _district_metadata(repository: Path) -> tuple[dict[str, dict[str, Any]], str]:
    acceptance = yaml.safe_load((repository / "config/p11_spatial_readiness_acceptance.yml").read_text())
    root = Path(acceptance["acceptance_path"]).parent
    path = root / "master_district_folds.parquet"
    rows = pq.read_table(path).to_pylist()
    if len(rows) != 1600 or len({row["scene_id"] for row in rows}) != 1600:
        raise InspectorError("district scene population mismatch")
    names: dict[str, str] = {}
    boundary = yaml.safe_load((repository / "config/p11_spatial_readiness.yml").read_text())["district_boundary"]
    try:
        import geopandas as gpd
        districts = gpd.read_file(boundary)
        names = {str(row.SIGUNGU_CD): str(row.SIGUNGU_NM) for row in districts.itertuples()}
    except Exception as exc:  # pragma: no cover - environment-specific driver failures
        raise InspectorError(f"district label read failed: {exc}") from exc
    return {
        str(row["scene_id"]): {
            "district_id": str(row["district_id"]),
            "district": names.get(str(row["district_id"]), str(row["district_id"])),
            "center": [float(row["center_x"]), float(row["center_y"])],
        }
        for row in rows
    }, sha256_file(path)


def _evaluation_root(contract: Mapping[str, Any], model: str) -> Path:
    return Path(contract["publication_root"]) / "execution_attempts" / P10_ATTEMPT_ID / "evaluations" / model


def build_rank_manifest(repository: Path) -> tuple[dict[str, Any], set[str]]:
    """Validate accepted P10 evidence and reconstruct all inspector rank bands."""
    contract_path = repository / "config/p10_evaluation.yml"
    contract = load_contract(contract_path)
    bindings = resolve_model_bindings(contract)
    _, galleries = evaluation_population(contract)
    scene_ids = [str(row["scene_id"]) for row in galleries]
    qualitative = make_qualitative_contract(contract, galleries)
    if qualitative["contract_id"] != P10_QUERY_CONTRACT_ID:
        raise InspectorError("qualitative query contract identity mismatch")
    published_qualitative = _json(Path(contract["publication_root"]) / "qualitative" / f"{P10_QUERY_CONTRACT_ID}.json")
    if published_qualitative != qualitative:
        raise InspectorError("qualitative query contract readback mismatch")
    acceptance_path = Path(contract["publication_root"]) / "execution_attempts" / P10_ATTEMPT_ID / "commit/evaluation_acceptance.json"
    acceptance = _json(acceptance_path)
    if acceptance.get("acceptance_id") != P10_ACCEPTANCE_ID or acceptance.get("status") != "PASS":
        raise InspectorError("P10 acceptance mismatch")
    attempt = _json(Path(contract["publication_root"]) / "execution_attempts" / P10_ATTEMPT_ID / "attempt.json")
    cache_manifest = Path(contract["prepared_input"]["root"]) / attempt["prepared_input_cache_id"] / "prepared_input_manifest.json"
    cache = P10PreparedInputCache.open(cache_manifest, verify_payloads=True)
    mask_scenes, masks = cache.nonlocal_masks()
    if mask_scenes != scene_ids:
        raise InspectorError("non-local mask population mismatch")
    districts, district_sha = _district_metadata(repository)
    if set(districts) != set(scene_ids):
        raise InspectorError("district and evaluation scene populations differ")
    scene_index = {scene: index for index, scene in enumerate(scene_ids)}
    required = set(qualitative["selected_scene_ids"])
    models: dict[str, Any] = {}
    for binding in bindings:
        root = _evaluation_root(contract, binding.configuration_id)
        result = _json(root / "evaluation.json")
        if result.get("acceptance_id") != binding.acceptance_id or result.get("checkpoint_id") != binding.checkpoint_id:
            raise InspectorError(f"P10 result binding mismatch: {binding.configuration_id}")
        arrays_path = root / "evaluation_embeddings_ranks_analysis.npz"
        with np.load(arrays_path) as arrays:
            embeddings = np.asarray(arrays["embeddings"], dtype=np.float32)[3200:]
            centers = np.asarray(arrays["centers"], dtype=np.float64)[3200:]
        if embeddings.shape != (1600, 128) or centers.shape != (1600, 2):
            raise InspectorError(f"P10 original-gallery shape mismatch: {binding.configuration_id}")
        committed = _json(root / "qualitative_retrieval.json")
        reproduced = _qualitative(binding, __import__("torch").from_numpy(embeddings), centers, scene_ids, qualitative, masks)
        if committed != reproduced:
            raise InspectorError(f"P10 qualitative ranking readback mismatch: {binding.configuration_id}")
        queries: dict[str, Any] = {}
        for query_scene in qualitative["selected_scene_ids"]:
            query_index = scene_index[query_scene]
            similarities = embeddings @ embeddings[query_index]
            distances = np.sqrt(((centers - centers[query_index]) ** 2).sum(axis=1))
            standard = [i for i in range(1600) if i != query_index]
            standard.sort(key=lambda i: (-float(similarities[i]), scene_ids[i]))
            nonlocal_indices = [i for i in standard if bool(masks[query_index, i])]
            if len(standard) != 1599 or any(float(distances[i]) < 2000.0 for i in nonlocal_indices):
                raise InspectorError(f"retrieval candidate contract failure: {query_scene}")
            settings: dict[str, Any] = {}
            for setting, indices in (("standard", standard), ("nonlocal", nonlocal_indices)):
                ranks = band_ranks(len(indices))
                bands: dict[str, Any] = {}
                for band, selected_ranks in ranks.items():
                    values = []
                    for rank in selected_ranks:
                        candidate = indices[rank - 1]
                        scene = scene_ids[candidate]
                        required.add(scene)
                        values.append({
                            "rank": rank, "scene_id": scene,
                            "similarity": float(similarities[candidate]),
                            "distance_m": float(distances[candidate]),
                        })
                    bands[band] = values
                settings[setting] = {"candidate_count": len(indices), "bands": bands}
            queries[query_scene] = settings
        models[binding.configuration_id] = {
            "label": MODEL_LABELS[binding.configuration_id], "acceptance_id": binding.acceptance_id,
            "checkpoint_id": binding.checkpoint_id, "embedding_sha256": result["embedding_sha256"],
            "arrays_sha256": sha256_file(arrays_path), "queries": queries,
        }
    query_rows = []
    for position, scene in enumerate(qualitative["selected_scene_ids"], start=1):
        query_rows.append({"index": position, "scene_id": scene, **districts[scene]})
    manifest = {
        "schema_version": SCHEMA_VERSION, "tool": TOOL_VERSION,
        "scientific_status": "qualitative inspection only; no model or checkpoint selection",
        "p10_acceptance_id": P10_ACCEPTANCE_ID, "p10_acceptance_sha256": sha256_file(acceptance_path),
        "p10_execution_attempt_id": P10_ATTEMPT_ID,
        "qualitative_contract_id": P10_QUERY_CONTRACT_ID,
        "qualitative_contract_sha256": sha256_file(Path(contract["publication_root"]) / "qualitative" / f"{P10_QUERY_CONTRACT_ID}.json"),
        "evaluation_split_acceptance_id": contract["accepted_evaluation"]["split_acceptance_id"],
        "gallery_id": contract["accepted_evaluation"]["gallery_id"],
        "gallery_count": 1600, "query_count": 10, "metric": "cosine_similarity",
        "metric_direction": "larger_is_more_similar", "nonlocal_exclusion_m": 2000,
        "band_contract": {
            "most": "rank 1", "top": "ranks 2-11",
            "middle": "10 contiguous ranks starting at floor((N-10)/2)+1",
            "bottom": "last 10 ranks",
        },
        "district_assignment_sha256": district_sha, "queries": query_rows, "models": models,
    }
    manifest["ranking_sha256"] = canonical_sha256(manifest["models"])
    return manifest, required


def _scene_assets(repository: Path, manifest: Mapping[str, Any], scene_ids: set[str], output: Path) -> dict[str, str]:
    contract = load_contract(repository / "config/p10_evaluation.yml")
    p3_root = Path(contract["inputs"]["p3_root"])
    index_path = next((p3_root / "index").glob("*/scene_to_shard.parquet"))
    index_rows = pq.read_table(index_path).to_pylist()
    by_scene = {str(row["scene_id"]): row for row in index_rows}
    if not scene_ids <= set(by_scene):
        raise InspectorError(f"P3 source scenes missing: {sorted(scene_ids - set(by_scene))[:3]}")
    # Populate metadata for non-query scenes from the accepted fold assignment.
    fold_root = Path(yaml.safe_load((repository / "config/p11_spatial_readiness_acceptance.yml").read_text())["acceptance_path"]).parent
    fold_rows = pq.read_table(fold_root / "master_district_folds.parquet")
    if fold_rows.num_rows != 1600:
        raise InspectorError("accepted fold population mismatch")
    district_names, _ = _district_metadata(repository)
    grouped: dict[str, list[str]] = defaultdict(list)
    for scene in sorted(scene_ids):
        grouped[str(by_scene[scene]["branch_id"])].append(scene)
    hashes: dict[str, str] = {}
    for branch_id in sorted(grouped):
        exemplar = by_scene[grouped[branch_id][0]]
        tar_path = p3_root / "shards" / branch_id / exemplar["payload_filename"]
        if sha256_file(tar_path) != exemplar["payload_sha256"]:
            raise InspectorError(f"P3 shard hash mismatch: {branch_id}")
        with tempfile.TemporaryDirectory(prefix="retrieval-inspector-") as temporary:
            temporary_path = Path(temporary)
            with tarfile.open(tar_path) as archive:
                buildings = _table(archive, "vector/building_observed.parquet")
                roads = _table(archive, "vector/road_observed.parquet")
                pois = _table(archive, "vector/poi_observed.parquet")
                relations = {str(row["scene_id"]): row for row in _table(archive, "relations/scene_relation_statistics.parquet")}
                raster_index = {str(row["scene_id"]): row for row in _table(archive, "raster/scene_raster_index.parquet")}
                _extract_zarr(archive, temporary_path)
            entity_groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"B": [], "R": [], "P": []})
            for entity_type, rows in (("B", buildings), ("R", roads), ("P", pois)):
                for row in rows:
                    scene = str(row["scene_id"])
                    if scene in scene_ids:
                        entity_groups[scene][entity_type].append(row)
            lc_group = zarr.open_group(str(temporary_path / "raster/scene_landcover.zarr"), mode="r")
            dem_group = zarr.open_group(str(temporary_path / "raster/scene_dem.zarr"), mode="r")
            for scene in grouped[branch_id]:
                raster = raster_index.get(scene)
                relation = relations.get(scene)
                if raster is None or relation is None or raster.get("split") != "evaluation":
                    raise InspectorError(f"P3 evaluation scene linkage invalid: {scene}")
                xmin, ymin = float(raster["xmin"]), float(raster["ymin"])
                index = int(raster["zarr_index"])
                groups = entity_groups[scene]
                vectors = []
                for entity_type in ("B", "R", "P"):
                    for row in sorted(groups[entity_type], key=lambda item: int(item["local_entity_id"])):
                        vectors.append({
                            "type": entity_type,
                            "geometry": _geometry(shapely.from_wkb(bytes(row["observed_geometry"])), xmin, ymin),
                        })
                fractions = np.asarray(lc_group["class_fraction"][index], dtype=np.float32)
                lc_valid = np.asarray(lc_group["valid_mask"][index], dtype=bool)
                lc = np.argmax(fractions, axis=0).astype(np.int16) + 1
                lc[~lc_valid] = 0
                composition = fractions[:, lc_valid].sum(axis=1) / max(int(lc_valid.sum()), 1)
                dem = np.asarray(dem_group["raw_mean_m"][index], dtype=np.float32)
                dem_valid = np.asarray(dem_group["valid_mask"][index], dtype=bool)
                dem_flat = [float(value) if valid else None for value, valid in zip(dem.ravel(), dem_valid.ravel(), strict=True)]
                dem_values = dem[dem_valid]
                building_area = sum(float(row.get("observed_area_m2") or 0) for row in groups["B"])
                road_length = sum(float(row.get("observed_length_m") or 0) for row in groups["R"])
                meta = district_names[scene]
                payload = {
                    "scene_id": scene, "district": meta["district"], "district_id": meta["district_id"],
                    "center": meta["center"], "bounds": [xmin, ymin, float(raster["xmax"]), float(raster["ymax"])],
                    "vectors": vectors,
                    "landcover": {"shape": [100, 100], "rle": _rle(lc.ravel()),
                                  "composition": [float(value) for value in composition]},
                    "dem": {"shape": [17, 17], "rle": _rle(dem_flat),
                            "min": float(dem_values.min()) if dem_values.size else None,
                            "mean": float(dem_values.mean()) if dem_values.size else None,
                            "max": float(dem_values.max()) if dem_values.size else None},
                    "summary": {
                        "building_count": len(groups["B"]), "building_area_m2": building_area,
                        "building_coverage": building_area / 250000.0,
                        "road_segment_count": len(groups["R"]), "road_length_m": road_length,
                        "poi_count": len(groups["P"]),
                        "poi_categories": _counter(groups["P"], "CLASS_L1_LABEL"),
                        "building_types": _counter(groups["B"], "A9"),
                        "building_structures": _counter(groups["B"], "A11"),
                        "road_ranks": _counter(groups["R"], "ROAD_RANK"),
                        "road_types": _counter(groups["R"], "ROAD_TYPE"),
                        "relations": {key.upper(): int(relation[f"{key}_edge_count"]) for key in ("sn", "cnt", "wit", "int", "con")},
                    },
                    "source": {"p3_branch_id": branch_id, "p3_payload_sha256": exemplar["payload_sha256"]},
                }
                raw = b"window.RETRIEVAL_SCENES=window.RETRIEVAL_SCENES||{};window.RETRIEVAL_SCENES[" + json.dumps(scene).encode() + b"]=" + _canonical(payload).rstrip() + b";window.dispatchEvent(new CustomEvent('retrieval-scene-loaded',{detail:" + json.dumps(scene).encode() + b"}));\n"
                target = output / "assets/scenes" / f"{scene}.js"
                _atomic_write(target, raw)
                hashes[scene] = hashlib.sha256(raw).hexdigest()
    return hashes


def validate_output(output: Path, expected_identity: str | None = None) -> dict[str, Any]:
    manifest = _json(output / "manifest.json")
    if expected_identity is not None and manifest.get("inspector_id") != expected_identity:
        raise InspectorError("inspector identity mismatch")
    if len(manifest.get("queries", [])) != 10 or set(manifest.get("models", {})) != set(MODEL_IDS):
        raise InspectorError("inspector model/query coverage invalid")
    required = {"index.html", "app.js", "style.css", "manifest.js", "manifest.json"}
    if not all((output / name).is_file() for name in required):
        raise InspectorError("inspector core asset missing")
    for scene, checksum in manifest["scene_asset_sha256"].items():
        path = output / "assets/scenes" / f"{scene}.js"
        if not path.is_file() or sha256_file(path) != checksum:
            raise InspectorError(f"scene asset readback failure: {scene}")
    html = (output / "index.html").read_text(encoding="utf-8")
    if "http://" in html or "https://" in html or "/mnt/" in html:
        raise InspectorError("HTML is not local/path-safe")
    return {"status": "PASS", "inspector_id": manifest["inspector_id"], "scene_asset_count": len(manifest["scene_asset_sha256"])}


def generate_inspector(repository: Path, output_root: Path, overwrite: bool = False) -> Path:
    repository = repository.resolve()
    rank_manifest, required = build_rank_manifest(repository)
    implementation = {
        name: sha256_file(repository / "tools/retrieval_inspector" / name)
        for name in ("inspector.py", "index.html", "style.css", "app.js")
    }
    identity_preimage = {
        "tool": TOOL_VERSION, "ranking_sha256": rank_manifest["ranking_sha256"],
        "p10_acceptance_sha256": rank_manifest["p10_acceptance_sha256"],
        "qualitative_contract_sha256": rank_manifest["qualitative_contract_sha256"],
        "implementation": implementation,
    }
    inspector_id = f"retrieval_inspector_{canonical_sha256(identity_preimage)[:24]}"
    destination = output_root.resolve() / inspector_id
    if destination.exists():
        if overwrite:
            shutil.rmtree(destination)
        else:
            validate_output(destination, inspector_id)
            return destination
    stage = Path(tempfile.mkdtemp(prefix=f".{inspector_id}.", dir=output_root.resolve()))
    try:
        for name in ("index.html", "style.css", "app.js"):
            shutil.copyfile(repository / "tools/retrieval_inspector" / name, stage / name)
        scene_hashes = _scene_assets(repository, rank_manifest, required, stage)
        final_manifest = {**rank_manifest, "inspector_id": inspector_id,
                          "identity_preimage": identity_preimage, "scene_asset_sha256": scene_hashes,
                          "scene_asset_count": len(scene_hashes), "render": {
                              "crs": "EPSG:5186", "extent_m": [500, 500], "north_up": True,
                              "landcover_colors": list(LC_COLORS), "dem_scale": "shared_current_comparison",
                          }}
        _atomic_write(stage / "manifest.json", _canonical(final_manifest))
        escaped = _canonical(final_manifest).decode("utf-8").replace("<", "\\u003c")
        _atomic_write(stage / "manifest.js", f"window.RETRIEVAL_MANIFEST={escaped};\n".encode())
        validate_output(stage, inspector_id)
        os.replace(stage, destination)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_output(destination, inspector_id)
    return destination
