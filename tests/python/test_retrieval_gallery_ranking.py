import numpy as np
import pytest

from retrieval_gallery_ranking import rank_gallery


def test_ties_self_and_exact_two_km_boundary():
    ids = ["query", "z", "a", "near"]
    embeddings = np.ones((4, 128), dtype=np.float32)
    xy = [[0, 0], [2000, 0], [3000, 0], [1999.999, 0]]
    result = rank_gallery(ids, xy, embeddings, ["query"])["query"]
    assert [ids[i] for i in result["standard"]["indices"]] == ["a", "near", "z"]
    assert [ids[i] for i in result["nonlocal"]["indices"]] == ["a", "z"]
    assert np.all(result["nonlocal"]["distances"] >= 2000)


def test_ten_by_ten_thousand_exact_ranking():
    rng = np.random.default_rng(19)
    ids = [f"s{i:05d}" for i in range(10000)]
    xy = rng.uniform(0, 30000, size=(10000, 2))
    embeddings = rng.normal(size=(10000, 128)).astype(np.float32)
    first = rank_gallery(ids, xy, embeddings, ids[:10])
    second = rank_gallery(ids, xy, embeddings, ids[:10])
    for query in ids[:10]:
        assert len(first[query]["standard"]["indices"]) == 9999
        for setting in ("standard", "nonlocal"):
            np.testing.assert_array_equal(first[query][setting]["indices"], second[query][setting]["indices"])
            scores = first[query][setting]["similarities"]
            assert np.all(scores[:-1] >= scores[1:])


def test_duplicate_and_zero_vectors_fail_closed():
    with pytest.raises(ValueError, match="identity"):
        rank_gallery(["a", "a"], [[0, 0], [1, 1]], np.ones((2, 128), dtype=np.float32), ["a"])
    with pytest.raises(ValueError, match="Zero"):
        rank_gallery(["a"], [[0, 0]], np.zeros((1, 128), dtype=np.float32), ["a"])
