"""Read and verify the saved XLSX; produce portable snapshots, never author XLSX."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def saved_tables(path: Path) -> dict:
    result = {}
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt XLSX")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [
                "".join(si.itertext())
                for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(
                    "s:si", NS
                )
            ]
        relationships = {
            r.get("Id"): r.get("Target")
            for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            target = relationships[sheet.get(f"{{{REL}}}id")]
            member = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath("xl/" + target)
            )
            if not member.startswith("xl/") or ".." in member.split("/"):
                raise ValueError("Invalid worksheet relationship")
            xml = ET.fromstring(archive.read(member))
            if xml.find(".//s:f", NS) is not None:
                raise ValueError("Unexpected formula; explicit preservation required")
            cells = {}
            width = 0
            for row in xml.findall("s:sheetData/s:row", NS):
                number = int(row.get("r"))
                if number < 8:
                    continue
                for cell in row.findall("s:c", NS):
                    column = 0
                    for letter in re.match("[A-Z]+", cell.get("r")).group():
                        column = column * 26 + ord(letter) - 64
                    width = max(width, column)
                    value = cell.find("s:v", NS)
                    kind = cell.get("t")
                    if kind == "s":
                        parsed = strings[int(value.text)]
                    elif kind == "inlineStr":
                        parsed = "".join(cell.find("s:is", NS).itertext())
                    elif kind == "str":
                        parsed = value.text if value is not None else None
                    elif value is None:
                        parsed = None
                    elif kind == "b":
                        parsed = value.text == "1"
                    else:
                        parsed = float(value.text)
                        if parsed.is_integer():
                            parsed = int(parsed)
                    cells[number, column] = parsed
            numbers = sorted({n for n, _ in cells if n > 8})
            result[sheet.get("name")] = {
                "headers": [cells.get((8, c)) for c in range(1, width + 1)],
                "rows": [
                    [cells.get((n, c)) for c in range(1, width + 1)] for n in numbers
                ],
                "freeze": xml.find(".//s:pane", NS) is not None,
                "tables": xml.find("s:tableParts", NS) is not None,
            }
        tables = [
            ET.fromstring(archive.read(name))
            for name in archive.namelist()
            if name.startswith("xl/tables/") and name.endswith(".xml")
        ]
        if len(tables) != 4 or any(t.find("s:autoFilter", NS) is None for t in tables):
            raise ValueError("Four filtered tables required")
    return result


def comparable(value, expected):
    if value in (None, "") and expected in (None, ""):
        return True
    # artifact-tool may retain Excel's leading literal escape in serialized text.
    return value == expected or (
        isinstance(expected, str)
        and expected.startswith("=")
        and value == "'" + expected
    )


def run(workbook: Path, prepared: Path, output: Path) -> dict:
    data = json.loads(prepared.read_text(encoding="utf-8"))
    workbook_sha = sha(workbook)
    sheets = saved_tables(workbook)
    specs = [
        ("Словарь", "words", "concepts.csv"),
        ("Медиа", "media", "media.csv"),
        ("Текст", "text", "text_candidates.csv"),
        ("Покрытие", "coverage", "coverage.csv"),
    ]
    if list(sheets) != [s[0] for s in specs]:
        raise ValueError("Unexpected sheet names/order")
    for name, key, _ in specs:
        actual = sheets[name]
        if actual["headers"] != data[key + "_headers"] or len(actual["rows"]) != len(
            data[key]
        ):
            raise ValueError("Sheet shape changed: " + name)
        if not actual["freeze"] or not actual["tables"]:
            raise ValueError("Missing table/frozen panes")
        for n, (row, expected) in enumerate(
            zip(actual["rows"], data[key], strict=True), 9
        ):
            for c, (value, wanted) in enumerate(zip(row, expected, strict=True), 1):
                if not comparable(value, wanted):
                    raise ValueError(
                        f"Saved export mismatch {name}!row{n}/column{c}: {value!r} != {wanted!r}"
                    )
    old_media_count = data.get("input_rows", {}).get("media", 0)
    if any(
        row[15] != "Нет" or row[3] != "Не назначено"
        for row in sheets["Медиа"]["rows"][old_media_count:]
    ):
        raise ValueError("Unexpected training admission/split")
    old_count = data.get("input_rows", {}).get(
        "words", data["stats"]["concepts"] - data["stats"]["new_visual_concepts"]
    )
    if any(
        row[6] not in (None, "") or row[7] not in (None, "")
        for row in sheets["Словарь"]["rows"][old_count:]
    ):
        raise ValueError("This batch contains no measured per-concept metrics")
    output.mkdir(parents=True, exist_ok=True)
    exports = []
    for name, _, filename in specs:
        target = output / filename
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";", lineterminator="\n")
            for row in [sheets[name]["headers"], *sheets[name]["rows"]]:
                writer.writerow(
                    [
                        "'" + v
                        if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                        else v
                        for v in row
                    ]
                )
        exports.append(
            {"file": filename, "sha256": sha(target), "bytes": target.stat().st_size}
        )
    reviewed_pages = set()
    overviewed_pages = set()
    for review in data["review_files"]:
        source = Path(review["path"])
        if sha(source) != review["sha256"]:
            raise ValueError("Review changed before queue export")
        review_data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(review_data, dict):
            continue
        for book in review_data.get("books", []):
            reviewed_pages.update(
                (book["filename"], page)
                for page in book.get("pages_visually_reviewed", [])
            )
            overviewed_pages.update(
                (book["filename"], page) for page in book.get("pages_overviewed", [])
            )
    queue = output / "review_queue.csv"
    with queue.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";", lineterminator="\n")
        writer.writerow(
            [
                "ID страницы",
                "Книга",
                "Страница PDF",
                "Полная сцена",
                "SHA сцены",
                "Просмотр агента",
                "Обзор страницы",
                "Полная семантическая разметка",
                "Допуск обучения",
            ]
        )
        for row in sheets["Медиа"]["rows"]:
            if row[16] != "PAGE_CONTEXT":
                continue
            book = row[7].split("; PDF ")[0]
            page = int(re.search(r"; PDF (\d+)", row[7]).group(1))
            writer.writerow(
                [
                    row[0],
                    book,
                    page,
                    row[2],
                    row[10],
                    "Просмотрено выборочно"
                    if (book, page) in reviewed_pages
                    else "Ожидается",
                    "Просмотрена обзорно"
                    if (book, page) in overviewed_pages
                    else "Ожидается",
                    "Не завершена",
                    "Нет",
                ]
            )
    exports.append(
        {"file": queue.name, "sha256": sha(queue), "bytes": queue.stat().st_size}
    )
    catalogue = {
        "schema": 2,
        "workbook_sha256": workbook_sha,
        "authoritative_file": "visual_lexicon.xlsx",
        "training_admitted": False,
        "stats": data["stats"],
        "sheets": sheets,
    }
    with (
        (output / "catalogue.json.gz").open("wb") as stream,
        gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as packed,
    ):
        packed.write(
            json.dumps(catalogue, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    exports.append(
        {
            "file": "catalogue.json.gz",
            "sha256": sha(output / "catalogue.json.gz"),
            "bytes": (output / "catalogue.json.gz").stat().st_size,
        }
    )
    report = {
        "schema": 2,
        "workbook_sha256": workbook_sha,
        "preserved_input_workbook_sha256": data["input_workbook_sha256"],
        "previous_prepared_history": data.get("previous_prepared_history"),
        "all_saved_cells_match": True,
        "formulas": 0,
        "tables_and_filters": 4,
        "training_started": False,
        "training_admitted": False,
        "stats": data["stats"],
        "review_inputs": data["review_files"],
        "overview_pages": len(overviewed_pages),
        "detailed_review_pages": len(reviewed_pages),
        "overview_coverage": data.get("overview_coverage", []),
        "deduplicated_evidence": data.get("deduplicated_evidence", []),
        "unresolved_proposals": data.get("unresolved", []),
        "omitted_cell_links_still_in_media": data.get(
            "omitted_cell_links_still_in_media", {}
        ),
        "spreadsheet_text_escapes": data.get("spreadsheet_text_escapes", []),
        "csv_policy": "UTF-8 BOM; semicolon; quoted multiline; literal leading =+-@ strings escaped, typed numbers unchanged",
        "exports": exports,
        "limits": data["stats"]["limits"],
    }
    (output / "catalogue_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if sha(workbook) != workbook_sha:
        raise ValueError("Workbook changed during verification")
    print(
        json.dumps(
            {
                "verified": True,
                "workbook_sha256": workbook_sha,
                "stats": data["stats"],
                "export_bytes": sum(e["bytes"] for e in exports),
            },
            ensure_ascii=False,
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.workbook, args.prepared, args.output)
