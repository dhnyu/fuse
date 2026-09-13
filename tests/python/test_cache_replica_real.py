"""Opt-in CPU qualification using a tiny subset of current immutable cache files."""
import json
import os
from pathlib import Path

import pytest
import torch

from artifact_protocol import sha256_file
from training_cache_storage import CacheInventory, cache_inventory, copy_replica, verify_replica
from training_prepared_cache import ProductionPreparedData, DSRasterCacheReader
from training_geometry_cache import GeometryCacheReader


@pytest.mark.skipif(os.environ.get("FUSE_TEST_REAL_CACHE_REPLICA") != "1", reason="explicit real-cache CPU qualification")
def test_real_ssd_subset_readers_bit_exact(tmp_path, monkeypatch):
    import training_cache_storage as storage
    source = Path('/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/prepared_cache/s09cache_dc4e9e271e40ffe8ae17967c')
    inventory = cache_inventory(source)
    production = json.loads((source/'production_cache_manifest.json').read_text())
    chosen = {}
    for row in production['entries']:
        s = row['spec']
        key = s['profile'] if s['role'].startswith('training') else s['role']
        if key in {'main_1.0x', 'weak_0.5x', 'strong_2.0x', 'validation_query', 'validation_gallery'}:
            chosen.setdefault(key, row)
    assert len(chosen) == 5
    names = {name for name in inventory.files if name.endswith('.json')}
    for row in chosen.values():
        names.update((f"prepared/{row['global_index']:06d}.pt",
                      f"geometry/entries/{row['record']['cache_key']}.pt", f"ds/entries/{row['ds']['cache_key']}.pt"))
    subset = CacheInventory(inventory.cache_id, inventory.acceptance_id,
                            {name: inventory.files[name] for name in sorted(names)})
    dest = tmp_path/'ssd'/source.name
    # A subset receipt can NEVER satisfy the unmocked production inventory.
    with monkeypatch.context() as patch:
        patch.setattr(storage, 'cache_inventory', lambda _: subset)
        copy_replica(source, dest)
        verify_replica(source, dest, full=True)
    with pytest.raises(storage.CacheStorageError, match='RECEIPT_INVALID'):
        verify_replica(source, dest)
    geometry = GeometryCacheReader(dest/'geometry/geometry_cache_manifest.json')
    ds = DSRasterCacheReader(dest)
    for key, row in chosen.items():
        s = row['spec']
        profile = key if key.endswith('x') else 'main_1.0x'
        reader = ProductionPreparedData(dest, profile, 8, verify_payloads=True)
        logical = 'training' if s['role'].startswith('training') else s['role']
        value = reader.sample(logical, s['scene_id'], s['view'])
        original = torch.load(source/f"prepared/{row['global_index']:06d}.pt", map_location='cpu', weights_only=False)['sample']
        assert torch.equal(value['entities']['local_entity_id'], original['entities']['local_entity_id'])
        role, scene, view = row['record']['lookup_key'].split('\0')
        magnitude, phase = geometry._get(role, scene, view)
        assert torch.isfinite(magnitude).all() and torch.isfinite(phase).all()
        raster = ds._get(row['ds']['role'], row['ds']['scene_id'], str(row['ds']['view_id']))
        assert raster.shape == (26, 100, 100) and torch.isfinite(raster).all()
    assert all(sha256_file(dest/name)==inventory.files[name]['sha256'] for name in names)
