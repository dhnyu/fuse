"""Prevent default-tool/current-artifact drift back to the 1600-only UI."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "tools")]
from retrieval_inspector.artifacts import LEGACY_ID, legacy_output, resolve_current, validate_current
from retrieval_inspector.inspector import InspectorError


def test_default_cli_is_the_actual_repo_local_10k_package():
    container = ROOT / "artifacts/retrieval-inspector"
    pointer = json.loads((container / "current.json").read_text())
    legacy = json.loads((container / "legacy.json").read_text())
    result = subprocess.run([sys.executable, "tools/render_retrieval_inspector.py"], cwd=ROOT,
        env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}, capture_output=True, text=True, check=True)
    entry = Path(result.stdout.strip())
    assert entry == ROOT / pointer["path"]
    assert entry.parent.parent == container / "current"
    assert pointer["inspector_id"] != legacy["inspector_id"] == LEGACY_ID
    assert pointer["gallery_count"] == 10000 and pointer["default_gallery"] == "expanded"
    manifest = json.loads((entry.parent / "manifest.json").read_text())
    assert manifest["default_gallery"] == "supplemental"
    assert manifest["galleries"]["supplemental"]["gallery_count"] == 10000
    assert manifest["galleries"]["canonical"]["gallery_count"] == 1600
    html = entry.read_text()
    for fragment in ('id="gallery"', 'id="stability"', 'value="supplemental" selected>Expanded 10,000', 'Canonical 1,600'):
        assert fragment in html
    assert 'http-equiv="refresh"' not in html and "/mnt/" not in html
    assert all((entry.parent / name).is_file() for name in ("app.js","style.css","manifest.js","diagnostics.js","artifact.json"))
    assert (entry.parent / "assets").is_symlink()
    validate_current(entry.parent)


@pytest.mark.parametrize("bad", ["legacy_id", "legacy_path", "wrong_default"])
def test_current_pointer_rejects_legacy_and_wrong_default(tmp_path, bad):
    root = tmp_path / "artifacts/retrieval-inspector"
    root.mkdir(parents=True)
    pointer = {"role":"current","inspector_id":"retrieval_inspector_fixture","gallery_count":10000,
               "default_gallery":"expanded","path":"artifacts/retrieval-inspector/current/fixture/index.html"}
    if bad == "legacy_id":
        pointer["inspector_id"] = LEGACY_ID
    elif bad == "legacy_path":
        pointer["path"] = "artifacts/retrieval-inspector/legacy/fixture/index.html"
    else:
        pointer["default_gallery"] = "canonical"
    (root / "current.json").write_text(json.dumps(pointer))
    with pytest.raises(InspectorError, match="Current pointer"):
        resolve_current(tmp_path, root)


def test_legacy_is_explicit_and_never_rebuilt():
    root = ROOT / "artifacts/retrieval-inspector"
    entry = legacy_output(ROOT, root)
    assert entry == root / "legacy" / LEGACY_ID / "index.html"
    assert entry.resolve() == (root / LEGACY_ID / "index.html").resolve()
    assert json.loads((entry.parent / "manifest.json").read_text())["gallery_count"] == 1600
    source = (ROOT / "tools/retrieval_inspector/artifacts.py").read_text()
    for forbidden in ("rank_gallery(", "build_rank_manifest(", "generate_inspector(", "torch.load(", "_scene_assets("):
        assert forbidden not in source
