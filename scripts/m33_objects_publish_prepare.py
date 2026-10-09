"""Prepare eight measured catalogue changes; XLSX authoring stays in Artifact Tool."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from lexicon_catalogue_export import saved_tables, sha
from m33_objects_data import write_json
from m33_verify_objects_evidence import verify


def build(workbook, previous_prepared, data, experiment, selection, output):
    if output.exists():
        raise ValueError("Fresh publication plan required")
    audit = verify(experiment, data)
    dataset = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    report = json.loads((experiment / "report.json").read_text(encoding="utf-8"))
    receipt = json.loads(selection.read_text(encoding="utf-8"))
    if (
        receipt["winner"]["checkpoint_sha256"] != report["checkpoint_sha256"]
        or sha(selection) != report["selection_receipt_sha256"]
    ):
        raise ValueError("Report does not belong to frozen development winner")
    media = json.loads((data / "image-registry.json").read_text(encoding="utf-8"))
    for item in media:
        if sha(Path(item["image_path"])) != item["image_sha256"]:
            raise ValueError("Registered lossless image changed")
    baseline_sha = sha(workbook)
    sheets = saved_tables(workbook)
    previous = json.loads(previous_prepared.read_text(encoding="utf-8"))
    prepared = copy.deepcopy(previous)
    prepared["previous_prepared_history"] = str(previous_prepared)
    prepared["input_workbook_sha256"] = baseline_sha
    prepared["input_rows"], prepared["input_headers"] = {}, {}
    for sheet, key in (
        ("Словарь", "words"),
        ("Медиа", "media"),
        ("Текст", "text"),
        ("Покрытие", "coverage"),
    ):
        prepared[key] = sheets[sheet]["rows"]
        prepared[key + "_headers"] = sheets[sheet]["headers"]
        prepared["input_rows"][key] = len(prepared[key])
        prepared["input_headers"][key] = prepared[key + "_headers"]
    changes, measured = [], {}
    for word, identifier in dataset["concept_ids"].items():
        matches = [i for i, r in enumerate(prepared["words"]) if r[0] == identifier]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous stable concept")
        index = matches[0]
        before = list(prepared["words"][index])
        after = list(before)
        stats = report["tests"]["object_final"]["by_concept"][word]
        measured[identifier] = stats
        after[5:8] = [
            "Требует доработки",
            stats["answerable_recall"],
            stats["false_assertions"],
        ]
        for column, split in ((8, "train"), (9, "final")):
            links = [
                r["image_path"]
                for r in media
                if r["concept_id"] == identifier
                and r["split"] == split
                and not r.get("parent")
            ]
            after[column] = "\n".join(
                dict.fromkeys([*(before[column] or "").splitlines(), *links])
            )
        after[10], after[11] = (
            report["checkpoint_sha256"],
            str(experiment / "report.json"),
        )
        correct = round(stats["examples"] * stats["answerable_recall"])
        overall = report["tests"]["object_final"]["all"]
        note = (
            f"2026-10-09. Расширение предметного блока. Победитель {receipt['winner']['name']}, {report['parameters']} параметров. "
            f"Новые контрольные рисунки: правильно названо {correct}/{stats['examples']}, уверенных ошибок по этому слову {stats['false_assertions']}. "
            f"Вся новая проверка: ответов {overall['accepted']}/{overall['examples']}, уверенных ошибок {overall['false_assertions']}. "
            f"Порог предметного ответа {report['thresholds']['object']}. Приёмка блока {'пройдена в ограниченной области' if report['object_gate'] else 'не пройдена'}. "
            "Рабочая модель не заменена. Нулевое число ошибок при отказе от всех ответов не означает знание. "
            "Разметка рисунков не слепая; фото, определения и весь учебник не обучались. "
            f"Все изображения, разбиения и происхождение: {data / 'image-registry.json'}"
        )
        after[12] = "\n".join(filter(None, [before[12], note]))
        if any(
            isinstance(v, str) and (len(v) > 32767 or v.startswith("=")) for v in after
        ):
            raise ValueError("Excel text safety/length limit exceeded")
        prepared["words"][index] = after
        changes.append(
            {"id": identifier, "row": index + 9, "before": before, "after": after}
        )
    prepared["object_pilot"] = {
        "training_started": True,
        "object_gate": report["object_gate"],
        "production_admitted": False,
        "report_sha256": sha(experiment / "report.json"),
        "image_registry_sha256": sha(data / "image-registry.json"),
        "updated_concepts": list(dataset["concept_ids"].values()),
        "selection_receipt_sha256": sha(selection),
    }
    output.mkdir()
    write_json(
        output / "changes.json",
        {
            "input_workbook_sha256": baseline_sha,
            "changes": changes,
            "measured_object_results": measured,
            "checkpoint_sha256": report["checkpoint_sha256"],
            "report_path": str(experiment / "report.json"),
            "object_gate": report["object_gate"],
        },
    )
    write_json(output / "arithmetic-audit.json", audit)
    with (output / "prepared.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(prepared, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
    return {
        "updated_concepts": len(changes),
        "registered_images": len(media),
        "input_workbook_sha256": baseline_sha,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "workbook",
        "previous-prepared",
        "data",
        "experiment",
        "selection",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.workbook,
                args.previous_prepared,
                args.data,
                args.experiment,
                args.selection,
                args.output,
            )
        )
    )
