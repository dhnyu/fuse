"""Central path helpers for FUSE data artifacts."""

from __future__ import annotations

import os
import platform
from pathlib import Path


DATA_ROOT_ENV = "FUSE_DATA_ROOT"
REPO_ROOT_ENV = "FUSE_REPO_ROOT"
DATA_ROOT_DEFAULT = Path("..") / "fusedata"
LEGACY_DATA_ROOT = Path("data")

DIRECTORIES = {
    "geodata": Path("geodata"),
    "grid_500m": Path("grid_500m"),
    "osm": Path("osm"),
    "osm_raw": Path("osm/raw"),
    "osm_canonical": Path("osm/canonical"),
    "osm_canonical_gpkg": Path("osm/canonical/gpkg"),
    "osm_canonical_parquet": Path("osm/canonical/parquet"),
    "osm_sampling": Path("osm/sampling"),
    "osm_metadata": Path("osm/metadata"),
    "osm_logs": Path("osm/logs"),
    "osm_tmp": Path("osm/tmp"),
    "sampling_global": Path("sampling_global"),
    "sampling_global_debug": Path("sampling_global/debug"),
    "streetview": Path("streetview"),
    "streetview_metadata": Path("streetview/metadata"),
    "streetview_panoramas_raw": Path("streetview/panoramas/raw"),
    "streetview_crops_front": Path("streetview/crops/front"),
    "streetview_crops_right": Path("streetview/crops/right"),
    "streetview_crops_rear": Path("streetview/crops/rear"),
    "streetview_crops_left": Path("streetview/crops/left"),
    "streetview_previews": Path("streetview/previews"),
    "streetview_logs": Path("streetview/logs"),
    "streetview_manifests": Path("streetview/manifests"),
    "streetview_debug": Path("streetview/debug"),
}

FILES = {
    "seoul_boundary": Path("geodata/seoul_boundary.gpkg"),
    "gadm_dir": Path("geodata/gadm"),
    "seoul_grid_500m": Path("grid_500m/seoul_grid_500m.gpkg"),
    "seoul_grid_500m_map": Path("grid_500m/seoul_grid_500m_map.png"),
    "osm_pbf": Path("osm/raw/geofabrik_south-korea-latest.osm.pbf"),
    "osm_roads_canonical": Path("osm/canonical/seoul_roads_canonical.gpkg"),
    "osm_roads_sampling_network": Path("osm/sampling/seoul_roads_sampling_network.gpkg"),
    "osm_poi_tmp_gpkg": Path("osm/tmp/seoul_osm_poi_extract.gpkg"),
    "samples_global_parquet": Path("sampling_global/seoul_road_network_samples.parquet"),
    "samples_global_leaflet": Path("sampling_global/seoul_road_network_sampling_map.html"),
    "gsv_candidate_pool_parquet": Path("streetview/metadata/gsv_candidate_pool.parquet"),
    "gsv_accepted_metadata": Path("streetview/metadata/gsv_accepted_metadata.parquet"),
    "gsv_rejected_metadata": Path("streetview/metadata/gsv_rejected_metadata.parquet"),
    "gsv_metadata_checkpoint": Path("streetview/metadata/gsv_metadata_checkpoint.parquet"),
    "gsv_metadata_rejection_summary": Path("streetview/metadata/gsv_metadata_rejection_summary.parquet"),
    "gsv_sampling_network_composition": Path("streetview/metadata/gsv_sampling_network_composition.parquet"),
    "gsv_final_manifest": Path("streetview/manifests/gsv_final_manifest.parquet"),
    "gsv_image_manifest": Path("streetview/manifests/gsv_image_manifest.parquet"),
    "gsv_final_coverage_leaflet": Path("streetview/metadata/gsv_final_coverage_map.html"),
    "gsv_diagnostics_report": Path("streetview/metadata/gsv_diagnostics_report.md"),
    "streetview_metadata_test": Path("streetview/metadata/gsv_metadata_test.parquet"),
    "streetview_metadata_pilot": Path("streetview/metadata/gsv_metadata_pilot_1000.parquet"),
    "streetview_metadata_summary": Path("streetview/metadata/gsv_metadata_pilot_summary.parquet"),
    "streetview_pano_duplication": Path("streetview/metadata/gsv_pano_duplication_counts.parquet"),
    "streetview_capture_year_distribution": Path("streetview/metadata/gsv_capture_year_distribution.parquet"),
    "streetview_manifest_100": Path("streetview/manifests/gsv_download_manifest_100.parquet"),
}


def find_repo_root(start: Path | None = None) -> Path:
    env_root = os.getenv(REPO_ROOT_ENV)
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if not (root / "config" / "paths.yml").exists():
            raise RuntimeError(f"{REPO_ROOT_ENV} does not look like the fuse repository: {root}")
        return root

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "paths.yml").exists() and (candidate / "R" / "road_environment_sampling.R").exists():
            return candidate
    raise RuntimeError(f"Could not locate the fuse repository root from {current}. Set {REPO_ROOT_ENV}.")


def repo_root() -> Path:
    return find_repo_root()


def data_root(create: bool = False) -> Path:
    root = repo_root()
    env_root = os.getenv(DATA_ROOT_ENV)
    if env_root:
        candidates = [Path(env_root).expanduser()]
    else:
        candidates = [root / DATA_ROOT_DEFAULT, root / LEGACY_DATA_ROOT]

    existing = [path for path in candidates if path.exists()]
    selected = existing[0] if existing else candidates[0]
    selected = selected.resolve()
    if create:
        selected.mkdir(parents=True, exist_ok=True)
    return selected


def data_path(*parts: str | os.PathLike[str], create_parent: bool = False, must_exist: bool = False) -> Path:
    path = data_root(create=create_parent).joinpath(*parts)
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Required data path does not exist: {path}")
    return path


def data_dir(key: str, create: bool = False, must_exist: bool = False) -> Path:
    try:
        path = data_root(create=create) / DIRECTORIES[key]
    except KeyError as exc:
        raise KeyError(f"Unknown FUSE data directory key: {key}") from exc
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if must_exist and not path.is_dir():
        raise FileNotFoundError(f"Required data directory does not exist: {path}")
    return path


def data_file(key: str, create_parent: bool = False, must_exist: bool = False) -> Path:
    try:
        rel = FILES[key]
    except KeyError as exc:
        raise KeyError(f"Unknown FUSE data file key: {key}") from exc
    return data_path(rel, create_parent=create_parent, must_exist=must_exist)


def ensure_core_dirs() -> None:
    for key in DIRECTORIES:
        data_dir(key, create=True)


def relative_to_repo_or_data(path: Path) -> str:
    resolved = path.resolve()
    for base in (repo_root(), data_root()):
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(resolved)


def environment_summary() -> dict[str, str | bool]:
    root = repo_root()
    droot = data_root()
    return {
        "repo_root": str(root),
        "data_root": str(droot),
        DATA_ROOT_ENV: os.getenv(DATA_ROOT_ENV, "<unset>"),
        REPO_ROOT_ENV: os.getenv(REPO_ROOT_ENV, "<unset>"),
        "legacy_data_present": (root / LEGACY_DATA_ROOT).exists(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
