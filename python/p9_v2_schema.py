"""Runtime JSON Schema validation for P9 v2 V2-A artifacts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_VERSION = "2.0.0"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "config" / "schemas"
SCHEMA_FILES = {
    "event": "p9_v2_event.schema.json",
    "ledger_header": "p9_v2_ledger_header.schema.json",
    "ledger_manifest": "p9_v2_ledger_manifest.schema.json",
    "tail_cache": "p9_v2_tail_cache.schema.json",
}


class P9V2SchemaError(ValueError):
    """Raised when an artifact fails its runtime schema."""


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    try:
        path = SCHEMA_ROOT / SCHEMA_FILES[name]
    except KeyError as error:
        raise KeyError(f"unknown P9 v2 schema: {name}") from error
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=None)
def validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        load_schema(name), format_checker=jsonschema.FormatChecker()
    )


def validate_instance(name: str, value: Any) -> None:
    errors = sorted(validator(name).iter_errors(value), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise P9V2SchemaError(f"{name} schema violation at {location}: {first.message}")
