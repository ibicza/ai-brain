"""Read-only append audit and guarded canonical catalogue publication."""

import argparse
import json
import os
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from lexicon_catalogue_export import comparable, saved_tables, sha


def verify(before, after, prepared, receipt):
    if receipt.exists():
        raise ValueError("Fresh receipt required")
    data = json.loads(prepared.read_text(encoding="utf-8"))
    if sha(before) != data["input_workbook_sha256"]:
        raise ValueError("User workbook changed")
    old, new = saved_tables(before), saved_tables(after)
    if list(old) != list(new):
        raise ValueError("Worksheet order changed")
    keys = {
        "Словарь": "words",
        "Медиа": "media",
        "Текст": "text",
        "Покрытие": "coverage",
    }
    for name, key in keys.items():
        if (
            old[name]["headers"] != new[name]["headers"]
            or new[name]["headers"] != data[key + "_headers"]
        ):
            raise ValueError("Catalogue header changed")
        # Account only for the documented blank/literal normalization.
        if len(new[name]["rows"]) != len(data[key]) or not all(
            all(comparable(a, b) for a, b in zip(row, expected, strict=True))
            for row, expected in zip(new[name]["rows"], data[key], strict=True)
        ):
            raise ValueError("Planned sheet values differ: " + name)
        for i, row in enumerate(old[name]["rows"]):
            if not all(
                comparable(a, b) for a, b in zip(row, new[name]["rows"][i], strict=True)
            ):
                raise ValueError("Existing saved cell changed")
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(before) as za, ZipFile(after) as zb:
        if za.read("xl/styles.xml") != zb.read("xl/styles.xml"):
            raise ValueError("Native style definitions changed")
        for n in range(1, 5):
            a, b = [
                ET.fromstring(z.read(f"xl/worksheets/sheet{n}.xml")) for z in (za, zb)
            ]
            ar, br = [xml.findall("s:sheetData/s:row", ns) for xml in (a, b)]
            for left, right in zip(ar, br):
                if left.attrib != right.attrib or [
                    (cell.get("r"), cell.get("s")) for cell in left
                ] != [(cell.get("r"), cell.get("s")) for cell in right]:
                    raise ValueError(
                        "Existing row visibility/height/cell styles changed"
                    )
                if int(left.get("r")) < 8 and ET.tostring(left) != ET.tostring(right):
                    raise ValueError("Existing instructions changed")
            for tag in (
                "sheetViews",
                "cols",
                "mergeCells",
                "sheetProtection",
                "conditionalFormatting",
                "drawing",
                "legacyDrawing",
            ):
                if [ET.tostring(x) for x in a.findall("s:" + tag, ns)] != [
                    ET.tostring(x) for x in b.findall("s:" + tag, ns)
                ]:
                    raise ValueError("Native feature changed: " + tag)
            old_validation = a.findall("s:dataValidations/s:dataValidation", ns)
            new_validation = b.findall("s:dataValidations/s:dataValidation", ns)
            if any(
                ET.tostring(x) not in [ET.tostring(y) for y in new_validation]
                for x in old_validation
            ):
                raise ValueError("Existing validation changed")
        for n in range(1, 5):
            a, b = [ET.fromstring(z.read(f"xl/tables/table{n}.xml")) for z in (za, zb)]
            for xml in (a, b):
                xml.attrib.pop("id", None)
                if n in (1, 2):
                    xml.attrib.pop("ref", None)
                    xml.find("s:autoFilter", ns).attrib.pop("ref", None)
            if ET.tostring(a) != ET.tostring(b):
                raise ValueError("Native table changed beyond expected appended rows")
    result = {
        "baseline_sha256": sha(before),
        "candidate_sha256": sha(after),
        "appended_concepts": len(new["Словарь"]["rows"]) - len(old["Словарь"]["rows"]),
        "appended_media_associations": len(new["Медиа"]["rows"])
        - len(old["Медиа"]["rows"]),
        "all_existing_cells_preserved": True,
        "native_styles_and_existing_features_preserved": True,
        "production_admitted": False,
    }
    receipt.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def publish(canonical, candidate, receipt, backup):
    expected = json.loads(receipt.read_text(encoding="utf-8"))
    if (
        sha(canonical) != expected["baseline_sha256"]
        or sha(candidate) != expected["candidate_sha256"]
        or backup.exists()
    ):
        raise ValueError("Guard changed or backup exists; do not overwrite")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(canonical, backup)
    if sha(backup) != expected["baseline_sha256"]:
        raise ValueError("Backup differs")
    sibling = canonical.with_name("visual_lexicon.composition-publication.xlsx")
    if sibling.exists():
        raise ValueError("Unreviewed pending catalogue already exists")
    shutil.copyfile(candidate, sibling)
    if (
        sha(sibling) != expected["candidate_sha256"]
        or sha(canonical) != expected["baseline_sha256"]
    ):
        raise ValueError("Inputs changed before publication")
    os.replace(sibling, canonical)
    if sha(canonical) != expected["candidate_sha256"]:
        raise ValueError("Published bytes differ")
    print(
        json.dumps(
            {
                "status": "CANONICAL_CATALOGUE_PUBLISHED",
                "sha256": sha(canonical),
                "backup": str(backup),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify", "publish"))
    for name in ("before", "after", "prepared", "receipt", "backup"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.mode == "verify":
        print(json.dumps(verify(args.before, args.after, args.prepared, args.receipt)))
    else:
        publish(args.before, args.after, args.receipt, args.backup)
