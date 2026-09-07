"""Runtime JSON Schema validation for current training artifacts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_VERSION = "2.0.0"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "config" / "schemas"
SCHEMA_FILES = {
    "event": "training_event.schema.json",
    "ledger_header": "training_ledger_header.schema.json",
    "ledger_manifest": "training_ledger_manifest.schema.json",
    "tail_cache": "training_tail_cache.schema.json",
    "immutable_locator": "training_immutable_locator.schema.json",
    "bundle_inventory": "training_bundle_inventory.schema.json",
    "run_bundle_manifest": "training_run_bundle_manifest.schema.json",
    "selection_contract": "training_selection_contract.schema.json",
    "finalization_result": "training_finalization_result.schema.json",
    "acceptance": "training_acceptance.schema.json",
    "acceptance_eligibility": "training_acceptance_eligibility.schema.json",
    "v1_retirement_manifest": "p9_v1_retirement_manifest.schema.json",
    "training_authority": "training_training_authority.schema.json",
    "checkpoint_commit": "training_checkpoint_commit.schema.json",
    "worker_ipc": "training_worker_ipc.schema.json",
}


class TrainingSchemaError(ValueError):
    """Raised when an artifact fails its runtime schema."""


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    try:
        path = SCHEMA_ROOT / SCHEMA_FILES[name]
    except KeyError as error:
        raise KeyError(f"unknown current training schema: {name}") from error
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
        raise TrainingSchemaError(f"{name} schema violation at {location}: {first.message}")
