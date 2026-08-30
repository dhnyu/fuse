"""Full-population P9 reader built on the accepted P3/P4/P5 contracts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from p7_training import P7ArtifactCatalog, P7Data


class P9Data(P7Data):
    """Use P7's immutable materialization methods without its prototype membership gate."""

    def __init__(self, catalog: P7ArtifactCatalog, preprocessing: dict[str, Any], vocabulary: dict[str, Any]) -> None:
        self.catalog, self.preprocessing, self.vocabulary = catalog, preprocessing, vocabulary
        self.members = {
            "training": sorted(catalog.k8),
            "validation": sorted(row["scene_id"] for row in catalog.gallery_rows["validation"]),
        }
        if len(self.members["training"]) != 2421 or len(set(self.members["validation"])) != 400:
            raise ValueError("P9 full population mismatch")
        if len(catalog.query_rows["validation"]) != 800:
            raise ValueError("P9 fixed validation-query population mismatch")
        self.cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.original_cache: dict[str, dict[str, Any]] = {}
        self.branch_delta_cache: dict[Path, dict[str, dict[str, list[dict[str, Any]]]]] = {}
        self.branch_candidate_ids: dict[Path, set[str]] = defaultdict(set)
        for scene_id in self.members["training"]:
            path, _ = catalog.p4_tar(scene_id)
            self.branch_candidate_ids[path].update(row["candidate_id"] for row in catalog.k8[scene_id])

    def evaluation_query(self, *_: Any, **__: Any) -> None:
        raise ValueError("evaluation-query access is prohibited in P9")
