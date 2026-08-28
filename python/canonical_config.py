"""Strict YAML loading and canonical scientific configuration hashing."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml


class StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_mapping(loader: StrictSafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _validate(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string mapping key at {path}: {key!r}")
            _validate(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite numeric value at {path}")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"unsupported YAML value at {path}: {type(value).__name__}")


def load_strict_yaml(path: str | Path) -> Any:
    value = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=StrictSafeLoader)
    _validate(value)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    _validate(value)
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_yaml_bytes(path: str | Path, excluded_top_level: tuple[str, ...] = ()) -> bytes:
    value = load_strict_yaml(path)
    if not isinstance(value, dict):
        raise ValueError("scientific configuration root must be a mapping")
    value = {key: item for key, item in value.items() if key not in excluded_top_level}
    return canonical_json_bytes(value)


def canonical_yaml_sha256(path: str | Path, excluded_top_level: tuple[str, ...] = ()) -> str:
    return hashlib.sha256(canonical_yaml_bytes(path, excluded_top_level)).hexdigest()
