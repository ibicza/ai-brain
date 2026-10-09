"""Read-only saved-XLSX audit: eight stable word IDs, F:M values only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from lexicon_catalogue_export import comparable, saved_tables, sha
from m33_objects_data import write_json


def verify(before: Path, after: Path, changes_file: Path, receipt: Path):
    if receipt.exists():
        raise ValueError("Fresh preservation receipt required")
    changes = json.loads(changes_file.read_text(encoding="utf-8"))
    if sha(before) != changes["input_workbook_sha256"]:
        raise ValueError("Baseline workbook changed")
    old, new = saved_tables(before), saved_tables(after)
    if old.keys() != new.keys():
        raise ValueError("Worksheet set changed")
    allowed = {c["row"] for c in changes["changes"]}
    if len(allowed) != 8 or {c["id"] for c in changes["changes"]} != {
        "vc0175",
        "vc0179",
        "vc0186",
        "vc0101",
        "vc0114",
        "vc0369",
        "vc0158",
        "vc0205",
    }:
        raise ValueError("Not the eight admitted stable IDs")
    differences = []
    for name in old:
        if old[name]["headers"] != new[name]["headers"] or len(
            old[name]["rows"]
        ) != len(new[name]["rows"]):
            raise ValueError("Saved sheet/header/row shape changed")
        for row, (left, right) in enumerate(
            zip(old[name]["rows"], new[name]["rows"], strict=True), 9
        ):
            for column, (a, b) in enumerate(zip(left, right, strict=True), 1):
                if not comparable(a, b):
                    if name != "Словарь" or row not in allowed or not 6 <= column <= 13:
                        raise ValueError("Unrelated saved cell changed")
                    differences.append([name, row, column])
    for change in changes["changes"]:
        row = change["row"] - 9
        if not all(
            comparable(a, b)
            for a, b in zip(old["Словарь"]["rows"][row], change["before"], strict=True)
        ) or not all(
            comparable(a, b)
            for a, b in zip(new["Словарь"]["rows"][row], change["after"], strict=True)
        ):
            raise ValueError("Exact planned record not preserved")
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(before) as z1, ZipFile(after) as z2:
        if z1.read("xl/styles.xml") != z2.read("xl/styles.xml"):
            raise ValueError("Native styles changed")
        for n in range(1, 5):
            a, b = [
                ET.fromstring(z.read(f"xl/worksheets/sheet{n}.xml")) for z in (z1, z2)
            ]
            left_rows, right_rows = [
                xml.findall("s:sheetData/s:row", ns) for xml in (a, b)
            ]
            if [r.attrib for r in left_rows] != [r.attrib for r in right_rows]:
                raise ValueError("Row heights/visibility changed")
            for left, right in zip(left_rows, right_rows, strict=True):
                if int(left.get("r")) < 8 and ET.tostring(left) != ET.tostring(right):
                    raise ValueError("Instructions/title changed")
                if [(c.get("r"), c.get("s")) for c in left] != [
                    (c.get("r"), c.get("s")) for c in right
                ]:
                    raise ValueError("Cell style bindings changed")
            for tag in (
                "sheetViews",
                "cols",
                "mergeCells",
                "dataValidations",
                "sheetProtection",
                "conditionalFormatting",
                "drawing",
                "legacyDrawing",
            ):
                if [ET.tostring(e) for e in a.findall("s:" + tag, ns)] != [
                    ET.tostring(e) for e in b.findall("s:" + tag, ns)
                ]:
                    raise ValueError("Native feature changed: " + tag)
        for n in range(1, 5):
            a, b = [ET.fromstring(z.read(f"xl/tables/table{n}.xml")) for z in (z1, z2)]
            for node in (a, b):
                node.attrib.pop("id", None)
            if ET.tostring(a) != ET.tostring(b):
                raise ValueError("Native table/filter changed")
    result = {
        "baseline_sha256": sha(before),
        "candidate_sha256": sha(after),
        "updated_concepts": 8,
        "changed_cells": len(differences),
        "all_other_cells_preserved": True,
        "styles_and_native_features_preserved": True,
        "four_filtered_tables_preserved": True,
        "training_started": True,
        "production_admitted": False,
        "differences": differences,
    }
    write_json(receipt, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "changes", "receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.before, args.after, args.changes, args.receipt)
    print(json.dumps({k: v for k, v in result.items() if k != "differences"}))
