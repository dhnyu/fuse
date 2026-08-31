"""Canonical JSON bytes and deterministic SHA-256 identities for P9 v2.

Numbers use an exact, exponent-free decimal representation. Finite Python
floats are interpreted as IEEE-754 binary64 values and expanded exactly in
base 10. This is intentionally more verbose than shortest-round-trip JSON,
but the byte contract is language-independent and straightforward to port.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from decimal import Decimal
from typing import Any


MAX_SAFE_INTEGER = (1 << 53) - 1


class CanonicalJSONError(ValueError):
    """Raised when a value is outside the P9 v2 canonical JSON domain."""


def _canonical_string(value: str) -> bytes:
    if unicodedata.normalize("NFC", value) != value:
        raise CanonicalJSONError("strings and object keys must already be NFC-normalized")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise CanonicalJSONError("lone Unicode surrogate code points are prohibited")
    output = bytearray(b'"')
    escapes = {
        '"': b'\\"',
        "\\": b"\\\\",
        "\b": b"\\b",
        "\f": b"\\f",
        "\n": b"\\n",
        "\r": b"\\r",
        "\t": b"\\t",
    }
    for char in value:
        encoded = escapes.get(char)
        if encoded is not None:
            output.extend(encoded)
        elif ord(char) < 0x20:
            output.extend(f"\\u{ord(char):04x}".encode("ascii"))
        else:
            output.extend(char.encode("utf-8"))
    output.extend(b'"')
    return bytes(output)


def _canonical_integer(value: int) -> bytes:
    if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
        raise CanonicalJSONError("integers must be within the interoperable JSON safe range")
    return str(value).encode("ascii")


def _canonical_float(value: float) -> bytes:
    if not math.isfinite(value):
        raise CanonicalJSONError("NaN and infinite values are prohibited")
    if abs(value) > MAX_SAFE_INTEGER:
        raise CanonicalJSONError("floats must remain within the interoperable JSON safe range")
    if value == 0.0:
        return b"0"
    decimal_value = Decimal.from_float(value)
    rendered = format(decimal_value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered.encode("ascii")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize the supported JSON value domain to one canonical byte string."""

    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int):
        return _canonical_integer(value)
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, str):
        return _canonical_string(value)
    if isinstance(value, list):
        return b"[" + b",".join(canonical_json_bytes(item) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalJSONError("object keys must be strings")
        keys = sorted(value)
        encoded = (
            _canonical_string(key) + b":" + canonical_json_bytes(value[key])
            for key in keys
        )
        return b"{" + b",".join(encoded) + b"}"
    raise CanonicalJSONError(f"unsupported canonical JSON value type: {type(value).__name__}")


def canonical_json_line(value: Any) -> bytes:
    """Return one canonical JSONL record with exactly one trailing newline."""

    return canonical_json_bytes(value) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def deterministic_id(prefix: str, value: Any) -> str:
    if not prefix or any(ord(char) > 0x7F for char in prefix):
        raise ValueError("identity prefix must be nonempty ASCII")
    return prefix + canonical_sha256(value)[:24]
