"""Append explicitly scoped lexical senses to the saved catalogue, without training.

Morphology is not sense disambiguation. Reviewed sense specifications are required;
spelling, aliases, frequencies and OCR alone never merge meanings or label occurrences.
All existing cells are immutable. Sources demonstrate spelling, not every chosen sense.
"""

from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import json
import re
from pathlib import Path


def load_increment():
    spec = importlib.util.spec_from_file_location(
        "lexicon_increment", Path(__file__).with_name("lexicon_catalogue_increment.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def merge_senses(
    words: list, text: list, specifications: list[dict], previous_registry=None
) -> tuple:
    """No implicit name/alias merge: either explicit existing ID or new sense ID."""
    inc = load_increment()
    result = copy.deepcopy(words)
    by_id = {row[0]: row for row in words}
    source_rows = {row[0]: row for row in text}
    sequence = max(int(row[0][2:]) for row in words if re.fullmatch(r"vc\d+", row[0]))
    identities, labels, mappings, deferred = {}, {}, [], []
    registry = {}
    for row in words:
        match = re.match(r"Лемма: (.+?)\. Смысл: (.+?)\.\n", str(row[12] or ""))
        if match:
            identity = (inc.normal(match[1]), match[2].casefold())
            if identity in registry and registry[identity] != row[0]:
                raise ValueError("Conflicting saved sense identities")
            registry[identity] = row[0]
    for old in previous_registry or []:
        identity = (inc.normal(old["lemma"]), old["sense_key"].casefold())
        if old["concept_id"] not in by_id or (
            identity in registry and registry[identity] != old["concept_id"]
        ):
            raise ValueError("Previous sense registry identity mismatch")
        registry[identity] = old["concept_id"]
    for specification in sorted(specifications, key=lambda s: s["reviewer"]):
        if (
            specification.get("training_started") is not False
            or specification.get("training_admitted") is not False
        ):
            raise ValueError("Lexical preparation cannot start/admit training")
        reviewer = specification["reviewer"]
        deferred.extend(specification.get("deferred", []))
        for sense in sorted(
            specification["concepts"],
            key=lambda s: (inc.normal(s["lemma"]), s["sense_key"].casefold()),
        ):
            lemma, key = sense["lemma"].strip(), sense["sense_key"].strip()
            word, description = sense["word"].strip(), sense["description"].strip()
            if (
                not lemma
                or not key
                or not word
                or not 1 <= len(description.split()) <= 20
            ):
                raise ValueError("Missing sense identity or invalid short description")
            if not sense.get("scope_note") or not sense.get("example"):
                raise ValueError("Sense requires explicit scope and example")
            if sense.get("authored_example") is not True:
                raise ValueError(
                    "This batch supports explicitly authored examples only"
                )
            source_ids = sense["source_text_ids"]
            if not source_ids or any(
                identifier not in source_rows for identifier in source_ids
            ):
                raise ValueError("Missing/unknown source text ID")
            # An orthographic relation is not a semantic witness. Its limits are explicit.
            if not any(
                inc.normal(source_rows[identifier][1]) == inc.normal(lemma)
                or inc.normal(lemma)
                in {
                    inc.normal(form.strip())
                    for form in str(source_rows[identifier][2] or "").split(";")
                }
                for identifier in source_ids
            ):
                raise ValueError("Lemma has no declared spelling/form witness")
            identity = (inc.normal(lemma), key.casefold())
            target = sense.get("existing_id")
            if target is not None and target not in by_id:
                raise ValueError("Unknown explicit existing concept ID")
            if identity in registry:
                if target is not None and target != registry[identity]:
                    raise ValueError("Explicit ID conflicts with saved sense registry")
                target = registry[identity]
            if target is not None and " ".join(
                str(by_id[target][2]).split()
            ) != " ".join(description.split()):
                raise ValueError(
                    "Existing concept definition differs; semantic reuse requires exact reviewed meaning"
                )
            if identity in identities:
                if identities[identity][1] != description or (
                    target is not None and identities[identity][0] != target
                ):
                    raise ValueError("Conflicting duplicate sense specification")
                continue
            if target is None:
                if inc.normal(word) in labels:
                    raise ValueError("New senses need distinct visible labels")
                sequence += 1
                target = f"vc{sequence:04d}"
                aliases = sense.get("aliases", [])
                if not isinstance(aliases, list) or any(
                    not isinstance(alias, str) for alias in aliases
                ):
                    raise ValueError("Aliases must be explicitly reviewed strings")
                names = list(
                    dict.fromkeys(([lemma] if word != lemma else []) + aliases)
                )
                paths = list(
                    dict.fromkeys(
                        path
                        for identifier in source_ids
                        for path in str(source_rows[identifier][12] or "").splitlines()
                        if path
                    )
                )
                note = (
                    f"Лемма: {lemma}. Смысл: {key}.\nГраница смысла: {sense['scope_note']}\n"
                    f"Авторский пример, не цитата учебника: {sense['example']}\n"
                    f"Кандидаты источника: {'; '.join(source_ids)}.\n"
                    "Источник подтверждает написание; не все вхождения размечены этим смыслом. "
                    "Словоформы и исходные контексты сохранены на листе Текст. "
                    "Смысл предложен агентом; требуется проверка. Обучение не запускалось.\n"
                    + "\n".join(paths[:5])
                )
                row = [
                    target,
                    word,
                    description,
                    sense["category"],
                    "; ".join(names),
                    "Сбор материалов",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    note,
                    None,
                ]
                result.append(inc.escape_new_row(row, "words", len(result) + 9, []))
                labels[inc.normal(word)] = target
            identities[identity] = (target, description)
            mappings.append(
                {
                    **copy.deepcopy(sense),
                    "concept_id": target,
                    "reviewer": reviewer,
                    "reused_existing_id": target in by_id,
                    "occurrences_disambiguated": False,
                    "training_admitted": False,
                }
            )
    if result[: len(words)] != words:
        raise ValueError("Existing words changed")
    return result, mappings, deferred


def csv_literal(value):
    return (
        "'" + value
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
        else value
    )


def run(
    workbook: Path,
    previous: Path,
    files: list[Path],
    corpus: Path,
    reviews_root: Path,
    output: Path,
) -> dict:
    inc = load_increment()
    sidecars = [
        output.parent / name
        for name in ("sense_catalogue.json", "word_review_queue.csv")
    ]
    if (
        output.exists()
        or any(p.exists() for p in sidecars)
        or output.resolve().is_relative_to(corpus.resolve())
    ):
        raise ValueError("Output must be fresh and outside sealed corpus")
    baseline_sha = inc.digest(workbook)
    previous_sha = inc.digest(previous)
    tables = inc.input_snapshot(inc.saved_tables(workbook))
    old = json.loads(previous.read_text(encoding="utf-8"))
    if (
        old.get("training_started") is not False
        or old.get("training_admitted") is not False
    ):
        raise ValueError("Previous batch has training admission")
    for key, headers in inc.HEADERS.items():
        if old[key + "_headers"] != headers or len(old[key]) != len(tables[key]):
            raise ValueError(
                "History schema/row count changed; explicit migration required"
            )
        if any(a[0] != b[0] for a, b in zip(old[key], tables[key], strict=True)):
            raise ValueError("History identity/order changed")
    roots = [corpus.resolve(), reviews_root.resolve()]
    for review in old["review_files"]:
        inc.checked_asset(review["path"], review["sha256"], roots)
    specifications, inputs = [], []
    for path in files:
        inputs.append({"path": str(path.resolve()), "sha256": inc.digest(path)})
        specifications.append(json.loads(path.read_text(encoding="utf-8")))
    previous_registry = old.get("sense_registry", old.get("sense_mappings", []))
    words, mappings, deferred = merge_senses(
        tables["words"], tables["text"], specifications, previous_registry
    )
    # Verify source files once; retain raw forms and contexts, do not classify all occurrences.
    sources = {}
    expected_sources = {}
    for media in tables["media"]:
        if media[2] and media[10]:
            path = str(Path(media[2]).resolve())
            if path in expected_sources and expected_sources[path] != media[10]:
                raise ValueError("Conflicting saved source hashes")
            expected_sources[path] = media[10]
    by_text = {row[0]: row for row in tables["text"]}
    for mapping in mappings:
        declared_paths = re.findall(
            r"[A-Za-z]:[\\/][^\s;,]*?\.(?:txt|json)", mapping["scope_note"]
        )
        declared_paths += mapping.get("source_files", [])
        for identifier in mapping["source_text_ids"]:
            declared_paths += str(by_text[identifier][12] or "").splitlines()
        for value in dict.fromkeys(declared_paths):
            if not value:
                continue
            path = Path(value).resolve()
            if not path.is_relative_to(corpus.resolve()) or not path.is_file():
                raise ValueError("Text source missing/escapes corpus")
            if str(path) not in expected_sources:
                raise ValueError("Text source has no saved media SHA")
            if str(path) not in sources:
                inc.checked_asset(
                    str(path), expected_sources[str(path)], [corpus.resolve()]
                )
                sources[str(path)] = expected_sources[str(path)]
    data = copy.deepcopy(old)
    counts = {key: len(rows) for key, rows in tables.items()}
    for key, rows in tables.items():
        data[key] = words if key == "words" else rows
    data.update(
        {
            "incremental": True,
            "lexical_senses": True,
            "input_workbook_sha256": baseline_sha,
            "input_rows": counts,
            "input_headers": copy.deepcopy(inc.HEADERS),
            "raw_assets": [],
            "training_started": False,
            "training_admitted": False,
            "sense_inputs": inputs,
            "sense_mappings": mappings,
            "sense_registry": previous_registry
            + [
                m
                for m in mappings
                if (m["lemma"], m["sense_key"])
                not in {(r["lemma"], r["sense_key"]) for r in previous_registry}
            ],
            "sense_deferred": deferred,
            "sense_source_files": [
                {"path": p, "sha256": s} for p, s in sources.items()
            ],
        }
    )
    data["previous_prepared_history"] = {
        "path": str(previous.resolve()),
        "sha256": previous_sha,
        "policy": "Saved values authoritative; earlier review metadata retained; no name-based sense merging.",
    }
    data["stats"].update(
        {
            "input_concepts": counts["words"],
            "input_media_rows": counts["media"],
            "concepts": len(words),
            "new_visual_concepts": 0,
            "new_word_concepts": len(words) - counts["words"],
            "new_media_rows": 0,
            "reviewed_occurrences": 0,
            "lexical_senses_reviewed": len(mappings),
            "lexical_existing_mappings": sum(m["reused_existing_id"] for m in mappings),
            "limits": "Explicit scoped lexical drafts, not all senses/occurrences verified; no training or new mastery metrics.",
        }
    )
    if inc.digest(workbook) != baseline_sha or inc.digest(previous) != previous_sha:
        raise ValueError("Saved input/history changed during preparation")
    for item in inputs + data["sense_source_files"] + data["review_files"]:
        if inc.digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("Source/specification changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    mapping_path = output.parent / "sense_catalogue.json"
    mapping_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "input_workbook_sha256": baseline_sha,
                "training_started": False,
                "training_admitted": False,
                "senses": mappings,
                "deferred": deferred,
                "source_files": data["sense_source_files"],
                "inputs": inputs,
                "limits": data["stats"]["limits"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    by_candidate = {}
    for mapping in mappings:
        for identifier in mapping["source_text_ids"]:
            by_candidate.setdefault(identifier, []).append(mapping["concept_id"])
    reasons = {r["text_id"]: r["reason"] for r in deferred}
    with (output.parent / "word_review_queue.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.writer(stream, delimiter=";", lineterminator="\n")
        writer.writerow(
            [
                "ID текста",
                "Лемма-кандидат",
                "Формы источника",
                "Предложенные ID смыслов",
                "Статус смысла",
                "Причина/ограничение",
                "Допуск обучения",
            ]
        )
        for row in tables["text"]:
            writer.writerow(
                [
                    csv_literal(value)
                    for value in [
                        row[0],
                        row[1],
                        row[2],
                        "; ".join(by_candidate.get(row[0], [])),
                        "Предложен; вхождения не разобраны"
                        if row[0] in by_candidate
                        else "Ожидает смыслового разбора",
                        reasons.get(
                            row[0],
                            "Словоформа/OCR и все значения требуют отдельной проверки",
                        ),
                        "Нет",
                    ]
                ]
            )
    print(json.dumps(data["stats"], ensure_ascii=True))
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--previous-prepared", type=Path, required=True)
    parser.add_argument("--senses", type=Path, action="append", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--reviews-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(
        args.workbook,
        args.previous_prepared,
        args.senses,
        args.corpus,
        args.reviews_root,
        args.output,
    )
