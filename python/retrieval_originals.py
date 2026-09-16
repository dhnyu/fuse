"""Bounded S10 reader of accepted P3 originals (dissertation scene construction).

Only I/O changes: one verified shard at a time, Arrow filtering before Python
conversion, and one raster extraction per shard. S09 preprocessing/tensorization
remain untouched. Callers restore canonical scene order before publication.
"""
from contextlib import ExitStack
from pathlib import Path
import io
import tarfile
import tempfile

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq
import zarr

from retrieval_artifacts import require


class OriginalReader:
    def __init__(self, catalog):
        self.catalog = catalog
        self.stack = ExitStack()
        self.path = None
        self.tables = {}
        self.groups = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.groups = None
        self.tables.clear()
        self.stack.close()
        self.path = None

    def ordered_ids(self, scene_ids):
        """Deterministic shard traversal, independent of caller/file listing order."""
        require(len(scene_ids) == len(set(scene_ids)), "DUPLICATE_ORIGINAL")
        return sorted(scene_ids, key=lambda s: (self.catalog.p3_by_scene[s]["branch_id"], s))

    def _open(self, scene_id):
        path, parent = self.catalog.p3_tar(scene_id)  # accepted index SHA, never filename equivalence
        if path != self.path:
            self.close()
            self.archive = self.stack.enter_context(tarfile.open(path))
            self.path = path
        return parent

    def _rows(self, name, scene_id):
        if name not in self.tables:
            member = self.archive.extractfile(name)
            require(member is not None, "P3_MEMBER:" + name)
            with member:
                self.tables[name] = pq.read_table(io.BytesIO(member.read()))
        table = self.tables[name]
        return table.filter(pc.equal(table["scene_id"], scene_id)).to_pylist()

    def _raster(self, index):
        if self.groups is None:
            temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="s10-shard-"))
            members = [m for m in self.archive.getmembers() if m.name.startswith(
                ("raster/scene_landcover.zarr/", "raster/scene_dem.zarr/"))]
            self.archive.extractall(temporary, members=members, filter="data")
            self.groups = tuple(zarr.open_group(str(Path(temporary) / "raster" / name), mode="r")
                                for name in ("scene_landcover.zarr", "scene_dem.zarr"))
        lc, dem = self.groups
        return {
            "landcover_class_fraction": np.asarray(lc["class_fraction"][index], dtype=np.float32),
            "landcover_valid_mask": np.asarray(lc["valid_mask"][index], dtype=np.uint8),
            "landcover_intentional_mask": np.zeros_like(np.asarray(lc["valid_mask"][index], dtype=np.uint8)),
            "landcover_valid_support": np.asarray(lc["valid_support_ratio"][index], dtype=np.float32),
            "dem_raw_mean": np.asarray(dem["raw_mean_m"][index], dtype=np.float64),
            "dem_valid_mask": np.asarray(dem["valid_mask"][index], dtype=np.uint8),
            "dem_valid_support": np.asarray(dem["valid_support_ratio"][index], dtype=np.float32),
        }

    def read(self, scene_id, *, vectors_only=False):
        parent = self._open(scene_id)
        vectors = []
        for entity_type, name in (("B", "building"), ("R", "road"), ("P", "poi")):
            for row in self._rows(f"vector/{name}_observed.parquet", scene_id):
                vectors.append({**row, "entity_type": entity_type})
        rows = self._rows("raster/scene_raster_index.parquet", scene_id)
        require(len(rows) == 1, "RASTER_INDEX")
        index = rows[0]
        center = ((vectors[0]["scene_center_x_5186"], vectors[0]["scene_center_y_5186"])
                  if vectors else ((index["xmin"]+index["xmax"])/2, (index["ymin"]+index["ymax"])/2))
        scene = {"scene_id": scene_id, "split": vectors[0]["split"] if vectors else index["split"],
                 "view_id": "original", "profile": None, "positive_scene_id": scene_id,
                 "parent": parent, "entities": sorted(vectors, key=lambda r: int(r["local_entity_id"])),
                 "center": center, "bounds": [index[k] for k in ("xmin", "ymin", "xmax", "ymax")]}
        # SVG uses vectors and center only. Never infer or rank in the renderer.
        if not vectors_only:
            scene.update(contexts={int(r["local_entity_id"]): r for r in self._rows("raster/object_raster_context.parquet", scene_id)},
                         relations=self._rows("relations/relation_edges.parquet", scene_id),
                         topology=self._rows("topology/source_topology.parquet", scene_id),
                         rasters=self._raster(int(index["zarr_index"])))
        return scene
