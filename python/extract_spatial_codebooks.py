#!/usr/bin/env python3
"""Extract the authoritative spatial categorical codebooks without Excel dependencies."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def workbook_rows(data: bytes) -> list[tuple[str, list[list[str]]]]:
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        strings: list[str] = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in node.iter(f"{{{NS['m']}}}t"))
                       for node in root.findall("m:si", NS)]
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relationships}
        output = []
        for sheet in workbook.find("m:sheets", NS):
            target = targets[sheet.attrib[f"{{{NS['r']}}}id"]].lstrip("/")
            path = target if target.startswith("xl/") else f"xl/{target}"
            root = ET.fromstring(book.read(path))
            rows = []
            for row in root.findall(".//m:sheetData/m:row", NS):
                cells: dict[int, str] = {}
                for cell in row.findall("m:c", NS):
                    letters = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                    column = 0
                    for char in letters:
                        column = column * 26 + ord(char) - 64
                    value_node = cell.find("m:v", NS)
                    value = "" if value_node is None else value_node.text or ""
                    if cell.attrib.get("t") == "s" and value:
                        value = strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
                    cells[column - 1] = value
                width = max(cells, default=-1) + 1
                rows.append([cells.get(index, "") for index in range(width)])
            output.append((sheet.attrib["name"], rows))
        return output


def inner_xlsx(path: Path, suffix: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(suffix)]
        if len(names) != 1:
            raise RuntimeError(f"Expected one {suffix} in {path}, found {len(names)}")
        return archive.read(names[0])


def parse_pairs(value: str, label_first: bool) -> list[tuple[str, str]]:
    pairs = []
    for item in re.split(r",\s*", value.strip()):
        if ":" not in item:
            continue
        left, right = (part.strip() for part in item.split(":", 1))
        label, code = (left, right) if label_first else (right, left)
        pairs.append((code.zfill(5) if code.isdigit() and len(code) <= 5 and label_first else code, label))
    return pairs


def source_entries(attribute: str, pairs: list[tuple[str, str]], provenance: str) -> list[dict]:
    by_label: dict[str, dict] = {}
    for position, (code, label) in enumerate(pairs):
        if label not in by_label:
            by_label[label] = {"attribute": attribute, "category_key": label,
                               "source_code": code, "source_codes": [code],
                               "source_label": label, "parent_key": None,
                               "source_order": position, "provenance": provenance}
        elif code not in by_label[label]["source_codes"]:
            by_label[label]["source_codes"].append(code)
    return list(by_label.values())


def code_entries(attribute: str, pairs: list[tuple[str, str]], provenance: str) -> list[dict]:
    by_code: dict[str, dict] = {}
    for position, (code, label) in enumerate(pairs):
        if code in by_code and by_code[code]["source_label"] != label:
            raise RuntimeError(f"Conflicting labels for {attribute} code {code}")
        if code not in by_code:
            by_code[code] = {"attribute": attribute, "category_key": code,
                             "source_code": code, "source_codes": [code],
                             "source_label": label, "parent_key": None,
                             "source_order": position, "provenance": provenance}
    return list(by_code.values())


def poi_entries(rows: list[list[str]], provenance: str) -> list[dict]:
    output = []
    seen = [set() for _ in range(6)]
    for row_number, row in enumerate(rows[2:], start=3):
        row = row + [""] * (12 - len(row))
        path: list[str] = []
        for level in range(6):
            label, code = row[level * 2].strip(), row[level * 2 + 1].strip()
            if not code or not label or label == "-":
                break
            path.append(code)
            key = "/".join(path)
            if key in seen[level]:
                continue
            seen[level].add(key)
            output.append({"attribute": f"CLASS_L{level + 1}", "category_key": key,
                           "source_code": code, "source_codes": [code],
                           "source_label": label,
                           "parent_key": "/".join(path[:-1]) or None,
                           "source_order": row_number, "provenance": provenance})
    return output


def poi_missing_markers(rows: list[list[str]]) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = {}
    for level in range(6):
        values = []
        seen = set()
        for row in rows[2:]:
            row = row + [""] * (12 - len(row))
            label, code = row[level * 2].strip(), row[level * 2 + 1].strip()
            if label == "-" and code and code not in seen:
                seen.add(code)
                values.append({"code": code, "label": "-", "state": "TERMINAL_DASH"})
        output[f"CLASS_L{level + 1}"] = values
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--building", required=True, type=Path)
    parser.add_argument("--road", required=True, type=Path)
    parser.add_argument("--poi", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    building_book = inner_xlsx(args.building, ".xlsx")
    sheets = dict(workbook_rows(building_book))
    table_rows = sheets[next(name for name in sheets if name.startswith("테이블정의서"))]
    ref_rows = sheets["참조코드"]
    purpose_text = next(row[11] for row in table_rows if len(row) > 11 and len(row) > 6 and row[6] == "A8")
    structure_text = next(row[2] for row in ref_rows if len(row) > 2 and row[1] == "건축물구조코드")
    purpose_reference_text = next(row[2] for row in ref_rows if len(row) > 2 and row[1] == "주요용도코드")
    building_hash = sha256(building_book)

    poi_book = inner_xlsx(args.poi, "POI_CL_DC_code.xlsx")
    poi_rows = workbook_rows(poi_book)[0][1]
    poi_hash = sha256(poi_book)

    entries = []
    purpose_pairs = parse_pairs(purpose_text, label_first=True) + parse_pairs(purpose_reference_text, label_first=False)
    structure_pairs = parse_pairs(structure_text, label_first=False)
    entries += source_entries("A9", purpose_pairs, "vworld_building_official_workbook:A8_and_reference")
    entries += code_entries("A11", structure_pairs, "vworld_building_official_workbook:structure_reference")
    for position, code in enumerate(["101", "102", "103", "104", "105", "106", "107"]):
        entries.append({"attribute": "ROAD_RANK", "category_key": code, "source_code": code,
                        "source_codes": [code], "source_label": code, "parent_key": None,
                        "source_order": position, "provenance": "ITS_nodelink:national_domain_audit"})
    for position, code in enumerate(["000", "001", "002", "003", "004"]):
        entries.append({"attribute": "ROAD_TYPE", "category_key": code, "source_code": code,
                        "source_codes": [code], "source_label": code, "parent_key": None,
                        "source_order": position, "provenance": "ITS_nodelink:national_domain_audit"})
    entries += poi_entries(poi_rows, "NGII_POI_CL_DC_code")

    value = {
        "schema_version": "1.0.0",
        "ordering": "official_source_order_then_missing_then_mask",
        "reserved_tokens": ["MISSING", "MASK"],
        "oov_policy": "hard_failure_no_oov_token",
        "sources": {
            "building": {"inner_workbook_sha256": building_hash, "archive": args.building.name},
            "road": {"archive_sha256": hashlib.sha256(args.road.read_bytes()).hexdigest(), "archive": args.road.name},
            "poi": {"inner_workbook_sha256": poi_hash, "archive": args.poi.name},
        },
        "missing_markers": {"poi_by_level": poi_missing_markers(poi_rows)},
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
