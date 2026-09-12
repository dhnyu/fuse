import copy, json
from pathlib import Path
import pytest, torch
from artifact_protocol import canonical_sha256, sha256_file
from training_prepared_cache import DSRasterCacheReader, DS_RASTER_CONTRACT_ID
from training_prepared_cache import _ds_entry_identity


def fixture(root):
    import hashlib

    root.mkdir()
    (root / "ds/entries").mkdir(parents=True)
    tensor = torch.zeros(26, 100, 100)
    raw = hashlib.sha256(tensor.numpy().tobytes()).hexdigest()
    identity = {
        "schema_version": "1.0.0",
        "contract_id": DS_RASTER_CONTRACT_ID,
        "geometry_layout_version": "3.0.0",
        "role": "training",
        "scene_id": "s",
        "view_id": "v",
        "source_cache_key": "a" * 64,
        "shape": [26, 100, 100],
        "dtype": "torch.float32",
        "raw_sha256": raw,
    }
    identity["cache_key"] = canonical_sha256(identity)
    payload = root / "ds/entries" / f"{identity['cache_key']}.pt"
    torch.save({"manifest": identity, "raster": tensor}, payload)
    ds = {
        "schema_version": "1.0.0",
        "status": "PASS",
        "contract_id": DS_RASTER_CONTRACT_ID,
        "entry_count": 1,
        "entries": [
            {
                **identity,
                "global_index": 0,
                "relative_path": "entries/" + payload.name,
                "payload_sha256": sha256_file(payload),
                "payload_size_bytes": payload.stat().st_size,
            }
        ],
    }
    h = canonical_sha256(ds)
    ds.update(cache_id="s09ds_" + h[:24], content_sha256=h)
    path = root / "ds/ds_cache_manifest.json"
    path.write_text(json.dumps(ds))
    production = {
        "cache_id": root.name,
        "status": "PASS",
        "parents": {"current": "yes"},
        "entry_count": 1,
        "entries": [
            {
                "global_index": 0,
                "ds": identity,
                "ds_sha256": sha256_file(payload),
                "ds_size": payload.stat().st_size,
            }
        ],
        "ds": {"cache_id": ds["cache_id"], "manifest_sha256": sha256_file(path)},
    }
    production["content_sha256"] = canonical_sha256(
        {k: v for k, v in production.items() if k != "cache_id"}
    )
    p = root / "production_cache_manifest.json"
    p.write_text(json.dumps(production))
    a = {
        "status": "PASS",
        "parents": production["parents"],
        "entry_count": 1,
        "cache_id": root.name,
        "manifest_sha256": sha256_file(p),
    }
    ah = canonical_sha256(a)
    a.update(content_sha256=ah, acceptance_id="s09ca_" + ah[:24])
    (root / "acceptance.json").write_text(json.dumps(a))
    return a, payload


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "missing",
        "wrong_id",
        "manifest",
        "payload",
        "acceptance",
        "historical_sibling",
    ],
)
def test_exact_ds_binding(tmp_path, fault):
    root = tmp_path / "cache"
    a, payload = fixture(root)
    if fault == "wrong_id":
        a["cache_id"] = "wrong"
        (root / "acceptance.json").write_text(json.dumps(a))
    if fault == "missing":
        (root / "ds/ds_cache_manifest.json").unlink()
    if fault == "manifest":
        (root / "ds/ds_cache_manifest.json").write_text("{}")
    if fault == "payload":
        payload.write_bytes(b"bad")
    if fault == "acceptance":
        (root / "acceptance.json").write_text("{}")
    if fault == "historical_sibling":
        fixture(tmp_path / "historical")
        (root / "ds/ds_cache_manifest.json").unlink()

    def run():
        reader = DSRasterCacheReader(root)
        return reader._get("training", "s", "v")

    if fault == "none":
        assert run().shape == (26, 100, 100)
    else:
        with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
            run()
