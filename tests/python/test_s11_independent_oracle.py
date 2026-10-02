"""Regression fixtures for the accepted verifier repair; no output producers."""
import json
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import pytest
from scipy.spatial.distance import cdist
from scipy.stats import rankdata, spearmanr
from s11_independent_oracle import independent_difference
from representation_analysis import cosine_block, eligibility, file_sha256

ROOT = Path(__file__).resolve().parents[2]
GENERATION = Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_representation/df3b397b64b6aeebde547b2e')


def test_equal_distance_and_adjacent_reversal_witnesses():
    f = json.loads((ROOT/'tests/fixtures/s11_euclidean_ties.json').read_text())
    v = np.array([f['query'], *f['vectors']], dtype=np.float64)
    oracle = independent_difference(v, 0)
    prod = cdist(v[:1], v)[0]
    old = np.linalg.norm(v-v[0], axis=1)  # required negative reference, tests only
    assert np.array_equal(oracle.view(np.uint64), prod.view(np.uint64))
    assert prod[1] < prod[2] and old[1] == old[2]
    assert prod[3] < prod[4] and old[3] > old[4]
    assert prod[5] == prod[6] and old[5] < old[6]
    assert np.array_equal(rankdata(oracle, method='average'), rankdata(prod, method='average'))
    assert not np.array_equal(rankdata(oracle), rankdata(old))
    assert rankdata(prod)[5] == rankdata(prod)[6]


def test_scalar_and_average_ties_unchanged():
    v = np.array([2., 0., 4., 3., 1.])
    assert np.array_equal(independent_difference(v, 0), np.abs(v-v[0]))
    assert np.array_equal(rankdata(independent_difference(v, 0)), [1, 4.5, 4.5, 2.5, 2.5])


@pytest.mark.parametrize('values', [np.ones((3, 2), np.float32), np.ones((3, 0)), np.array([np.nan])])
def test_oracle_fail_closed(values):
    with pytest.raises(ValueError):
        independent_difference(values, 0)


@pytest.fixture(scope='module')
def real_inputs():
    lock = json.loads((ROOT/'config/s11_representation_analysis.lock.json').read_text())
    vectors = lock['parents']['fm_vectors']
    assert file_sha256(vectors['path']) == vectors['sha256']
    manifest = json.loads((GENERATION/'descriptor_acceptance/accepted/manifest.json').read_text())
    path = GENERATION/'descriptor_acceptance/accepted/descriptors.parquet'
    assert file_sha256(path) == manifest['files']['descriptors.parquet']
    raw = pq.read_table(path)
    return np.load(vectors['path']), raw


@pytest.mark.parametrize('query,descriptor,negative', [
    (0, 'poi_l2_composition', True),
    (4499, 'building_use_composition', True),
    (0, 'landcover_composition', False),
])
def test_preserved_real_query_regressions(real_inputs, query, descriptor, negative):
    x, raw = real_inputs
    records = raw[descriptor].to_pylist()
    valid = np.array([v is not None for v in records])
    dimension = len(next(v for v in records if v is not None))
    v = np.array([r if r is not None else [0.]*dimension for r in records], dtype=np.float64)
    mask = valid.copy(); mask[query] = False
    scores = cosine_block(x, [query])[0, mask]
    prod = cdist(v[[query]], v)[0, mask]
    oracle = independent_difference(v, query)[mask]
    old = np.linalg.norm(v-v[query], axis=1)[mask]
    assert np.array_equal(prod.view(np.uint64), oracle.view(np.uint64))
    assert np.array_equal(rankdata(prod), rankdata(oracle))
    block = GENERATION/f'alignment_blocks/{query//32:04d}'
    manifest = json.loads((block/'manifest.json').read_text())
    assert file_sha256(block/'metrics.parquet') == manifest['files']['metrics.parquet']
    saved = pq.read_table(block/'metrics.parquet', filters=[('query_index','=',query),
        ('descriptor','=',descriptor), ('mode','=','standard'), ('region','=','rho')]).to_pylist()[0]
    rs, rd = rankdata(scores), rankdata(oracle)
    cs, cd = rs-rs.mean(), rd-rd.mean()
    manual = np.sum(cs*cd)/np.sqrt(np.sum(cs*cs)*np.sum(cd*cd))
    assert abs(spearmanr(scores, oracle).statistic-saved['value']) <= 2e-12
    assert abs(manual-saved['value']) <= 2e-12
    assert np.count_nonzero(prod != old) > 0
    if negative:
        assert abs(spearmanr(scores, old).statistic-saved['value']) > 2e-12
        assert np.count_nonzero(rankdata(prod) != rankdata(old)) > 0
    else:
        assert np.array_equal(rankdata(prod), rankdata(old))
