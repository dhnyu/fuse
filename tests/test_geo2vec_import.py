#!/usr/bin/env python3
"""Smoke test for importing GeoNeuralRepresentation / Geo2Vec.

This test intentionally does not run any embedding training. It verifies that
the external repository is present, PyTorch is importable, and list2vec can be
imported from the external codebase.
"""

from __future__ import annotations

import sys
from pathlib import Path


EXTERNAL_REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")

    require(
        EXTERNAL_REPO.exists() and EXTERNAL_REPO.is_dir(),
        f"GeoNeuralRepresentation repository not found: {EXTERNAL_REPO}",
    )
    require(
        (EXTERNAL_REPO / "runners" / "list2embedding.py").exists(),
        f"list2embedding.py not found under external repository: {EXTERNAL_REPO}",
    )

    sys.path.insert(0, str(EXTERNAL_REPO))

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "Required dependency missing: torch. Activate/install a PyTorch "
            "environment before running Geo2Vec integration tests."
        ) from exc

    print(f"torch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")

    try:
        from runners.list2embedding import list2vec
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import list2vec from "
            f"{EXTERNAL_REPO / 'runners' / 'list2embedding.py'}. "
            "Check GeoNeuralRepresentation dependencies and sys.path setup."
        ) from exc

    require(callable(list2vec), "Imported list2vec is not callable.")
    print("Imported list2vec successfully.")


if __name__ == "__main__":
    main()
