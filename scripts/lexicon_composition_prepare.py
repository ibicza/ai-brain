"""Append explicitly scoped concept senses; existing saved rows remain immutable."""

import argparse
import copy
import gzip
import json
import re
from pathlib import Path

import numpy as np
from lexicon_catalogue_export import saved_tables, sha
from lexicon_catalogue_increment import HEADERS, input_snapshot
from PIL import Image


def prepare(workbook, previous, vocabulary, output, experiment):
    if output.exists():
        raise ValueError("Fresh additions required")
    baseline = sha(workbook)
    data = copy.deepcopy(json.loads(previous.read_text(encoding="utf-8")))
    tables = input_snapshot(saved_tables(workbook))
    spec = json.loads(vocabulary.read_text(encoding="utf-8"))
    for key, headers in HEADERS.items():
        if data[key + "_headers"] != headers:
            raise ValueError("Unsupported catalogue history schema")
        data[key] = copy.deepcopy(tables[key])
    by_id = {r[0]: r for r in tables["words"]}
    for row in spec["existing"]:
        if row["id"] not in by_id or by_id[row["id"]][1] != row["word"]:
            raise ValueError("Existing meaning identity changed")
    names = {r[1] for r in tables["words"]}
    sequence = max(
        int(r[0][2:]) for r in tables["words"] if re.fullmatch(r"vc\d+", r[0])
    )
    mappings = []
    for i, concept in enumerate(spec["additions"], 1):
        if (
            concept["word"] in names
            or not 1 <= len(concept["description"].split()) <= 20
        ):
            raise ValueError("Duplicate sense or oversized description")
        names.add(concept["word"])
        identifier = f"vc{sequence + i:04d}"
        trained = bool(concept.get("course_answer"))
        note = "Явно ограниченный смысл. Определение не доказывает узнавание. Невидимое на конкретном изображении остаётся неизвестным."
        note += (
            " Эксперимент только на процедурных фигурах, не на животных или фотографиях."
            if trained
            else " В этом эксперименте распознавание этой части или свойства не обучалось."
        )
        if concept.get("source"):
            note += " Источник: " + concept["source"]
        row = [
            identifier,
            concept["word"],
            concept["description"],
            concept["category"],
            concept["alias"],
            "Требует доработки" if trained else "Запланировано",
            None,
            None,
            str(experiment / "dataset.npz") if trained else None,
            None,
            None,
            None,
            note,
            None,
        ]
        data["words"].append(row)
        mappings.append(
            {
                "concept_id": identifier,
                **concept,
                "training_scope": "procedural color/shape/pattern"
                if trained
                else "not trained",
            }
        )
    # Preserve exact full-frame pixels and the explicitly named target, not
    # an unlabeled scene falsely presented as an isolated object crop.
    with gzip.open(
        experiment / "dataset-records.json.gz", "rt", encoding="utf-8"
    ) as stream:
        records = json.load(stream)
    arrays = np.load(experiment / "dataset.npz", allow_pickle=False)
    new_media = []
    asset_root = experiment.parent / "catalogue-media"
    for mapping in mappings:
        if not mapping.get("course_answer"):
            continue
        word_row = next(row for row in data["words"] if row[0] == mapping["concept_id"])
        for split in ("train", "final", "combinations", "transfer"):
            task = "color" if mapping["course_answer"] == "тёмно-зелёный" else "pattern"
            count = 0
            for index, record in enumerate(records[split]["records"]):
                image_index = int(arrays[split + "_image_index"][index])
                item = records[split]["scenes"][image_index]["items"][record["side"]]
                if (
                    record["task"] != task
                    or item["hidden"]
                    or item[task] != mapping["course_answer"]
                ):
                    continue
                target = ("левый", "правый")[record["side"]]
                filename = asset_root / split / (str(image_index) + ".png")
                filename.parent.mkdir(parents=True, exist_ok=True)
                pixel = arrays[split + "_pixels"][image_index]
                if not filename.exists():
                    Image.fromarray(pixel).save(filename)
                if not np.array_equal(
                    np.asarray(Image.open(filename).convert("RGB")), pixel
                ):
                    raise ValueError("Saved illustration differs from training input")
                column = 8 if split == "train" else 9
                word_row[column] = "\n".join(
                    filter(None, [word_row[column], str(filename)])
                )
                new_media.append(
                    [
                        f"cmp-v2-{mapping['concept_id']}-{split}-{image_index}-{record['side']}",
                        mapping["concept_id"],
                        str(filename),
                        "train" if split == "train" else "regression",
                        "Признак указанного предмета",
                        "Процедурный рисунок",
                        f"{target} предмет: {mapping['course_answer']}",
                        f"composition-v2/{record['scene_id']}; exact RGB 96x96; task={task}; side={record['side']}",
                        "Собственный процедурный генератор",
                        f"composition-v2/{record['scene_id']}",
                        sha(filename),
                        "Проверено по генератору; не независимая семантическая разметка",
                        f"Вопрос вне изображения: {record['question']}",
                        "Да",
                        "Процедурный oracle + проверка точных пикселей",
                        "Только процедурный эксперимент" if split == "train" else "Нет",
                        "Полный кадр эксперимента",
                        None,
                        None,
                    ]
                )
                count += 1
                if count == 3:
                    break
            if count == 0 and split == "combinations" and task == "color":
                # Held pairs contain only green and blue. Never invent dark-green
                # examples or alter a sealed evaluation set to fill a catalogue.
                continue
            if count != 3:
                raise ValueError("Insufficient exact visual examples for concept")
    data["media"].extend(new_media)
    data["composition_media_registry"] = {
        "kind": "own_procedural_attribute_pilot",
        "asset_root": str(asset_root),
        "dataset_path": str(experiment / "dataset.npz"),
        "dataset_sha256": sha(experiment / "dataset.npz"),
        "records_path": str(experiment / "dataset-records.json.gz"),
        "records_sha256": sha(experiment / "dataset-records.json.gz"),
        "rows": {row[0]: row for row in new_media},
        "production_admitted": False,
        "book_training_admitted": False,
    }
    pilot = json.loads((experiment / "result.json").read_text(encoding="utf-8"))
    data["composition_pilot"] = {
        "training_started": True,
        "production_admitted": False,
        "scope": pilot["scope"],
        "model_status": pilot["status"],
        "candidate_checkpoint_sha256": pilot["checkpoint_sha256"],
        "report_path": str(experiment / "result.json"),
        "report_sha256": sha(experiment / "result.json"),
    }
    data.update(
        {
            "incremental": True,
            "input_workbook_sha256": baseline,
            "input_rows": {k: len(v) for k, v in tables.items()},
            "input_headers": HEADERS,
            "training_started": False,
            "training_admitted": False,
            "composition_vocabulary": {
                "specification_sha256": sha(vocabulary),
                "mappings": mappings,
                "existing": spec["existing"],
                "observation_policy": spec["observation_policy"],
            },
        }
    )
    data["stats"].update(
        {
            "input_concepts": len(tables["words"]),
            "concepts": len(data["words"]),
            "new_word_concepts": len(mappings),
            "media_rows": len(data["media"]),
            "new_visual_concepts": 0,
            "new_media_rows": len(new_media),
            "reviewed_occurrences": 0,
        }
    )
    if sha(workbook) != baseline:
        raise ValueError("Workbook changed during preparation")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    (output.parent / "vocabulary-mapping.json").write_text(
        json.dumps(data["composition_vocabulary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "existing_words": len(tables["words"]),
                "added_senses": len(mappings),
                "input_workbook_sha256": baseline,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workbook", "previous", "vocabulary", "output", "experiment"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    prepare(
        args.workbook.resolve(),
        args.previous.resolve(),
        args.vocabulary.resolve(),
        args.output.resolve(),
        args.experiment.resolve(),
    )
