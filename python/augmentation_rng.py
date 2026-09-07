"""P4 domain-separated SHA-256 counter draws (p4-augmentation-v2)."""

from __future__ import annotations

import hashlib
import math
import struct
import unicodedata
from collections.abc import Sequence

VERSION = "p4-augmentation-v2"
NAMESPACE = "training-bank"
NONE = "NONE"
DOMAINS = frozenset({
    "removal_fraction", "entity_selection", "receiver_selection",
    "geometry_jitter_gate", "geometry_jitter_value", "geometry_simplification",
    "categorical_mask", "categorical_replacement", "lane_perturbation",
    "landcover_mask", "landcover_seed", "landcover_frontier", "landcover_reseed",
    "dem_gaussian",
})


def _field(value: object, *, optional: bool = False) -> str:
    if value is None and optional:
        return NONE
    if isinstance(value, bool):
        raise ValueError("boolean is not a canonical integer field")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("canonical integers are unsigned")
        text = str(value)
    else:
        text = unicodedata.normalize("NFC", str(value))
    if not text or "|" in text or "\n" in text or "\r" in text:
        raise ValueError("invalid canonical seed field")
    return text


def canonical_payload(profile_id: str, scene_id: str, master_view_id: int,
                      operation: str, entity_id: object | None = None,
                      attempt: int | None = None) -> bytes:
    fields = (
        VERSION, NAMESPACE, _field(profile_id), _field(scene_id),
        _field(master_view_id), _field(operation),
        _field(entity_id, optional=True), _field(attempt, optional=True),
    )
    return "|".join(fields).encode("utf-8")


def base_digest(profile_id: str, scene_id: str, master_view_id: int,
                operation: str, entity_id: object | None = None,
                attempt: int | None = None) -> bytes:
    return hashlib.sha256(canonical_payload(
        profile_id, scene_id, master_view_id, operation, entity_id, attempt
    )).digest()


def counter_block(digest: bytes, domain: str, draw_index: int, counter: int = 0) -> bytes:
    if len(digest) != 32:
        raise ValueError("base digest must contain 32 bytes")
    if domain not in DOMAINS:
        raise ValueError(f"unregistered P4 draw domain: {domain}")
    if draw_index < 0 or counter < 0 or draw_index >= 2**64 or counter >= 2**64:
        raise ValueError("draw index/counter outside uint64")
    encoded = domain.encode("utf-8")
    if len(encoded) >= 2**16:
        raise ValueError("domain exceeds uint16 length")
    material = digest + b"\x00" + struct.pack(">H", len(encoded)) + encoded
    material += struct.pack(">QQ", draw_index, counter)
    return hashlib.sha256(material).digest()


def uniform_integer(digest: bytes, domain: str, draw_index: int, n: int) -> int:
    if n <= 0 or n > 2**64:
        raise ValueError("uniform integer range must be 1..2^64")
    if n == 1:
        return 0
    limit = 2**64 - (2**64 % n)
    counter = 0
    while True:
        x = int.from_bytes(counter_block(digest, domain, draw_index, counter)[:8], "big")
        if x < limit:
            return x % n
        counter += 1


def uniform_binary64(digest: bytes, domain: str, draw_index: int, *, open_interval: bool = False) -> float:
    x = int.from_bytes(counter_block(digest, domain, draw_index, 0)[:8], "big")
    m = x >> 11
    return (m + 0.5) * 2.0**-53 if open_interval else m * 2.0**-53


def standard_normal(digest: bytes, domain: str, draw_index: int) -> float:
    u1 = uniform_binary64(digest, domain, 2 * draw_index, open_interval=True)
    u2 = uniform_binary64(digest, domain, 2 * draw_index + 1, open_interval=True)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def sample_without_replacement(values: Sequence[str], k: int, digest: bytes,
                               domain: str) -> list[str]:
    ordered = sorted((unicodedata.normalize("NFC", str(value)) for value in values), key=lambda x: x.encode("utf-8"))
    if len(set(ordered)) != len(ordered):
        raise ValueError("candidate identities must be unique")
    if k < 0 or k > len(ordered):
        raise ValueError("invalid sample size")
    work = list(ordered)
    for j in range(k):
        offset = uniform_integer(digest, domain, j, len(work) - j)
        chosen = j + offset
        work[j], work[chosen] = work[chosen], work[j]
    return sorted(work[:k], key=lambda x: x.encode("utf-8"))


def removal_count(fraction: float, eligible_count: int) -> int:
    if eligible_count < 0 or not math.isfinite(fraction):
        raise ValueError("invalid removal inputs")
    return min(eligible_count, max(0, math.floor(fraction * eligible_count)))
