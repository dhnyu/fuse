#!/usr/bin/env python3
"""Inspect GeoNeuralRepresentation defaults without running training."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"


FILES = [
    "main.py",
    "runners/list2embedding.py",
    "runners/learn_shape_rep.py",
    "runners/learn_location_rep.py",
    "models/Geo2Vec.py",
    "models/MP_Sampling.py",
    "models/sample_function.py",
    "utils/data_loader.py",
]


def literal_default(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left = literal_default(node.left)
        right = literal_default(node.right)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left * right
    if isinstance(node, ast.IfExp):
        return ast.unparse(node)
    if isinstance(node, ast.Call):
        return ast.unparse(node)
    if isinstance(node, ast.Attribute):
        return ast.unparse(node)
    if isinstance(node, ast.Name):
        return node.id
    return ast.unparse(node)


def argparse_defaults(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defaults: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        arg_name = str(node.args[0].value).lstrip("-").replace("-", "_")
        for keyword in node.keywords:
            if keyword.arg == "default":
                defaults[arg_name] = literal_default(keyword.value)
    return defaults


def function_defaults(path: Path, function_name: str) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            arg_names = [arg.arg for arg in node.args.args]
            defaults = node.args.defaults
            return {
                name: literal_default(default)
                for name, default in zip(arg_names[-len(defaults) :], defaults)
            }
    return {}


def implementation_flags(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    return {
        "contains_DataLoader": "DataLoader(" in text,
        "contains_pin_memory_true": "pin_memory=True" in text,
        "contains_random_split": "random_split(" in text,
        "contains_MP_sample": "MP_sample(" in text,
        "contains_Geo2Vec_Dataset": "Geo2Vec_Dataset(" in text,
        "contains_poly_embedding_layer": "poly_embedding_layer" in text,
        "contains_out_of_sample_encoder": bool(re.search(r"encoder|encode", text, re.IGNORECASE))
        and "poly_embedding_layer" not in text,
    }


def main() -> None:
    report: dict[str, object] = {
        "external_repo": str(REPO),
        "argparse_defaults": {},
        "function_defaults": {},
        "implementation_flags": {},
    }
    for rel in FILES:
        path = REPO / rel
        if not path.exists():
            continue
        if rel.endswith(".py"):
            report["argparse_defaults"][rel] = argparse_defaults(path)
            report["implementation_flags"][rel] = implementation_flags(path)

    report["function_defaults"]["runners/list2embedding.py:list2vec"] = function_defaults(
        REPO / "runners/list2embedding.py", "list2vec"
    )
    report["function_defaults"]["models/Geo2Vec.py:Geo2Vec_Model.__init__"] = function_defaults(
        REPO / "models/Geo2Vec.py", "__init__"
    )
    report["function_defaults"]["models/MP_Sampling.py:MP_sample"] = function_defaults(
        REPO / "models/MP_Sampling.py", "MP_sample"
    )
    report["function_defaults"]["models/sample_function.py:sample_signed_distance"] = function_defaults(
        REPO / "models/sample_function.py", "sample_signed_distance"
    )
    report["function_defaults"]["models/sample_function.py:sample_bounding_distance"] = function_defaults(
        REPO / "models/sample_function.py", "sample_bounding_distance"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
