"""Exact projection/RNG regressions against the corrected synchronous contract."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import torch

from canonical_config import canonical_json_bytes
from training_support import derive_seed, seed_payload, state_content_digest
from training_family_inputs import (EntitySeedBytes, segments, check_sample, project,
                                    projected_collate, family_modality_assignments)
from test_training_family_projection import CONFIG, fixture


def old_segments(offsets, rows):
    values = [torch.arange(int(offsets[i]), int(offsets[i + 1])) for i in rows]
    indices = torch.cat(values) if values else torch.empty(0, dtype=torch.int64)
    return indices, torch.tensor([0, *torch.tensor([len(x) for x in values],
                                dtype=torch.int64).cumsum(0).tolist()])


@pytest.mark.parametrize("seed", range(30))
def test_segments_exact(seed):
    gen = torch.Generator().manual_seed(seed)
    lengths = torch.randint(0, 12, (seed,), generator=gen)
    offsets = torch.cat((torch.zeros(1, dtype=torch.int64), lengths.cumsum(0)))
    for rows in (torch.arange(seed), torch.randperm(seed, generator=gen),
                 torch.arange(0, seed, 2), torch.empty(0, dtype=torch.int64)):
        assert all(torch.equal(a, b) for a, b in zip(segments(offsets, rows),
                                                    old_segments(offsets, rows)))


def test_segments_reject_bad_indices():
    with pytest.raises(ValueError):
        segments(torch.tensor([0, 1]), torch.tensor([0.0]))
    with pytest.raises(ValueError):
        segments(torch.tensor([2, 1]), torch.tensor([0]))
    assert segments(torch.tensor([0]), torch.tensor([]))[0].dtype == torch.int64


@pytest.mark.parametrize("epoch", [0, 1, 9, 10, 95, 200])
@pytest.mark.parametrize("rank", [0, 1])
@pytest.mark.parametrize("view", [0, 1])
@pytest.mark.parametrize("scene", ['scene_a', 'quote"\\\n', '\uac00\ub098', 'local_entity_id'])
def test_seed_bytes_digest_gate_exact(epoch, rank, view, scene):
    for operation in ("entity-gate", "available-modality"):
        encoder = EntitySeedBytes(CONFIG, epoch, view, rank, scene, operation)
        for identity in [-1, 0, 1, 9, 10, 123456, 2**63 - 1]:
            fields = dict(epoch=epoch, global_rank=rank, worker_id=0,
                          operation=operation, scene_id=scene,
                          local_entity_id=identity, view_role=view)
            expected = canonical_json_bytes(seed_payload(CONFIG, "modality-mask", **fields))
            assert encoder.payload(identity) == expected
            assert hashlib.sha256(encoder.payload(identity)).digest() == hashlib.sha256(expected).digest()
            actual = encoder.seed(identity)
            assert actual == derive_seed(CONFIG, "modality-mask", **fields)
            assert (actual >> 10) * 2.0**-53 == (derive_seed(CONFIG, "modality-mask", **fields) >> 10) * 2.0**-53


def test_seed_invalid_fixed_and_dynamic_fields_fail():
    cfg = copy.deepcopy(CONFIG)
    cfg['parents']['scene_index_id'] = float('nan')
    with pytest.raises(ValueError):
        EntitySeedBytes(cfg, 1, 0, 0, 'scene', 'entity-gate')
    encoder = EntitySeedBytes(CONFIG, 1, 0, 0, 'scene', 'entity-gate')
    for value in [True, 0.0, '0', None]:
        with pytest.raises(ValueError):
            encoder.payload(value)


@pytest.mark.parametrize("family", ['FM','A1','A2','A3','A4','A5','SSV','DS',*[f'B{i}' for i in range(1,10)]])
def test_retention_nonalias_and_ring_failure(family):
    source = fixture()
    original = state_content_digest(source)
    projected, _ = project(source, family)
    projected['geometry']['part_coordinates_xy_m'].fill_(100)
    assert state_content_digest(source) == original
    source['geometry']['ring_component_index'][0] = 1
    with pytest.raises(ValueError, match='ring owner'):
        check_sample(source)


def test_ring_validation_empty_and_holes():
    s = fixture()
    s['geometry']['ring_is_hole'][0] = 1
    check_sample(s)
    check_sample(fixture(()))


@pytest.mark.parametrize('family', ['FM','B2','B3','B4','B5','B6','B7'])
def test_multipart_hole_and_sparse_geometry_projection(family):
    s = fixture()
    g = s['geometry']
    ep = torch.tensor([0, 2, 3, 3, 4])
    pc = torch.tensor([0, 3, 6, 8, 11])
    er = torch.tensor([0, 3, 3, 3, 4])
    g.update(entity_part_offsets=ep, entity_component_offsets=ep.clone(),
             part_coordinate_offsets=pc, component_coordinate_offsets=pc.clone(),
             entity_coordinate_offsets=pc[ep], entity_ring_offsets=er,
             ring_coordinate_start=torch.tensor([0, 3, 6, 9]),
             ring_coordinate_end=torch.tensor([3, 6, 9, 12]),
             ring_component_index=torch.tensor([0, 0, 1, 3]),
             ring_is_hole=torch.tensor([0, 1, 0, 0], dtype=torch.uint8))
    for key in ('part_coordinates_xy_m', 'part_coordinates_xy_m_scientific'):
        g[key] = torch.arange(22, dtype=torch.float64).reshape(11, 2)
    for key in ('ring_coordinates_xy_m', 'ring_coordinates_xy_m_scientific'):
        g[key] = torch.arange(24, dtype=torch.float64).reshape(12, 2)
    check_sample(s)
    p, m = project(s, family)
    parts, expected_ep = old_segments(ep, m['retained_rows'])
    coords, expected_pc = old_segments(pc, parts)
    rings, expected_er = old_segments(er, m['retained_rows'])
    rcoords, expected_rp = old_segments(torch.tensor([0, 3, 6, 9, 12]), rings)
    actual = p['geometry']
    for key, expected in [('entity_part_offsets', expected_ep),
                          ('part_coordinate_offsets', expected_pc),
                          ('entity_ring_offsets', expected_er),
                          ('ring_coordinate_start', expected_rp[:-1]),
                          ('ring_coordinate_end', expected_rp[1:])]:
        assert torch.equal(actual[key], expected)
    assert torch.equal(actual['part_coordinates_xy_m'], g['part_coordinates_xy_m'][coords])
    assert torch.equal(actual['ring_coordinates_xy_m'], g['ring_coordinates_xy_m'][rcoords])
    assert torch.equal(actual['ring_is_hole'], g['ring_is_hole'][rings])


REFERENCE = json.loads((Path(__file__).parents[1] / 'fixtures/s09_corrected_input_reference.json').read_text())


@pytest.mark.parametrize('case', REFERENCE['cases'])
def test_frozen_corrected_all_family_inputs_and_masks(case):
    p, m = project(fixture(case['types']), case['family'])
    assert state_content_digest((p, m)) == case['projection_sha']
    batch = projected_collate([(p, m)], {})
    assert state_content_digest(batch) == case['batch_sha']
    for key, expected in case['mask_sha'].items():
        epoch, rank, view = map(int, key.split(','))
        assert state_content_digest(family_modality_assignments(batch, CONFIG, epoch, view, rank)) == expected
