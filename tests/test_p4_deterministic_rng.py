import hashlib
import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from p4_deterministic_rng import (
    base_digest, canonical_payload, counter_block, removal_count,
    sample_without_replacement, standard_normal, uniform_binary64, uniform_integer,
)


def test_payload_nfc_field_order_and_sentinels():
    left = canonical_payload("main_1.0x", "sce\u0301ne", 0, "geometry", None, None)
    right = canonical_payload("main_1.0x", "sc\u00e9ne", 0, "geometry", None, None)
    assert left == right
    assert left.decode().endswith("|geometry|NONE|NONE")
    with pytest.raises(ValueError):
        canonical_payload("bad|profile", "scene", 0, "op")


def test_counter_block_is_exact_big_endian_contract():
    digest = bytes(range(32))
    domain = b"entity_selection"
    expected = hashlib.sha256(digest + b"\0" + struct.pack(">H", len(domain)) + domain + struct.pack(">QQ", 7, 9)).digest()
    assert counter_block(digest, domain.decode(), 7, 9) == expected


def test_uniform_integer_and_binary64_replay():
    digest = base_digest("main_1.0x", "scene", 3, "removal")
    assert [uniform_integer(digest, "entity_selection", i, 17) for i in range(8)] == [
        uniform_integer(digest, "entity_selection", i, 17) for i in range(8)
    ]
    value = uniform_binary64(digest, "removal_fraction", 0)
    bits = struct.pack(">d", value)
    assert bits == struct.pack(">d", uniform_binary64(digest, "removal_fraction", 0))
    assert 0 <= value < 1
    assert 0 < uniform_binary64(digest, "removal_fraction", 0, open_interval=True) < 1


def test_gaussian_uses_fresh_pair_without_spare_cache():
    digest = base_digest("strong_2.0x", "scene", 15, "dem")
    first = standard_normal(digest, "dem_gaussian", 0)
    second = standard_normal(digest, "dem_gaussian", 1)
    assert math.isfinite(first) and math.isfinite(second) and first != second
    assert (first, second) == (
        standard_normal(digest, "dem_gaussian", 0),
        standard_normal(digest, "dem_gaussian", 1),
    )


def test_partial_fisher_yates_ignores_input_order():
    digest = base_digest("weak_0.5x", "scene", 1, "removal")
    values = ["e10", "e2", "e1", "e9"]
    assert sample_without_replacement(values, 3, digest, "entity_selection") == sample_without_replacement(
        list(reversed(values)), 3, digest, "entity_selection"
    )


@pytest.mark.parametrize("fraction,n,expected", [
    (0.9, 0, 0), (0.9, 1, 0), (1.0, 1, 1), (0.0999, 10, 0),
    (0.1, 10, 1), (0.25, 7, 1), (2.0, 7, 7),
])
def test_floor_removal_count(fraction, n, expected):
    assert removal_count(fraction, n) == expected
