"""Generate the pre-declared 500-task semantic black-box battery."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.heldout import (
    make_semantic_key,
    verify_semantic_uniqueness,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("held-out target must be absent")
    selectors = json.loads(
        (ROOT / "config/m33_final_source_selectors.json").read_text(encoding="utf-8")
    )
    counts = selectors["task_schema"]
    rows = []
    rows.extend(_kinematics(counts["kinematics"]))
    rows.extend(_biology(counts["biology"]))
    rows.extend(_history(counts["history"]))
    rows.extend(_java(counts["java"]))
    keys = tuple(item.pop("semantic_key") for item in rows)
    uniqueness = verify_semantic_uniqueness(keys)
    if uniqueness["semantic_key_count"] != counts["minimum_semantically_unique"]:
        raise ValueError("sealed held-out task count mismatch")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            canonical_json({**row, **asdict(key)}) + "\n"
            for row, key in zip(rows, keys, strict=True)
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(canonical_json(uniqueness))
    return 0


def _row(bundle_id, operation, target, request, expected_status, index):
    key = make_semantic_key(
        operation_type=operation,
        target_record_id=target,
        requested_unknown=request.get("unknown"),
        givens={
            name: value.get("value", "")
            for name, value in request.get("givens", {}).items()
        },
        units={
            name: value.get("unit_id", "")
            for name, value in request.get("givens", {}).items()
        },
        conditions=tuple(request.get("conditions", ())),
        expected_answer_semantics=f"{expected_status}:{operation}:{target}:{index}",
    )
    return {
        "bundle_id": bundle_id,
        "request": request,
        "expected_status": expected_status,
        "expected": {},
        "semantic_key": key,
    }


def _kinematics(count):
    rows = []
    unknowns = ("v", "v0", "a", "t")
    for index in range(count):
        target = f"sealed-unsupported-kinematics-rule-{index:03d}"
        unknown = unknowns[index % len(unknowns)]
        givens = {
            "v": {"value": str(index + 1), "unit_id": "m-per-s"},
            "t": {"value": str((index % 17) + 1), "unit_id": "s"},
        }
        request = {
            "operation": "EQUATION_SOLVE",
            "rule_id": target,
            "unknown": unknown,
            "givens": givens,
            "conditions": (["constant acceleration"] if index % 5 else []),
        }
        rows.append(
            _row(
                "m33-kinematics",
                "EQUATION_SOLVE",
                target,
                request,
                "INSUFFICIENT_EVIDENCE",
                index,
            )
        )
    return rows


def _biology(count):
    operations = ("DEFINITION", "TAXONOMY", "PART_WHOLE", "SOURCE_ATTRIBUTION")
    rows = []
    for index in range(count):
        operation = operations[index % len(operations)]
        target = f"sealed-unsupported-biology-{index:03d}"
        request = {"operation": operation}
        if operation == "DEFINITION":
            request["term"] = target
        elif operation in {"TAXONOMY", "PART_WHOLE"}:
            request["subject_id"] = target
        else:
            request["record_id"] = target
        rows.append(
            _row(
                "m33-biology",
                operation,
                target,
                request,
                "INSUFFICIENT_EVIDENCE",
                index,
            )
        )
    return rows


def _history(count):
    operations = ("CHRONOLOGY", "SOURCE_ATTRIBUTION", "INTERPRETATIONS")
    rows = []
    for index in range(count):
        operation = operations[index % len(operations)]
        target = f"sealed-unsupported-history-{index:03d}"
        request = {"operation": operation}
        if operation == "CHRONOLOGY":
            request["record_ids"] = [target]
        else:
            request["record_id"] = target
        rows.append(
            _row(
                "m33-history",
                operation,
                target,
                request,
                "INSUFFICIENT_EVIDENCE",
                index,
            )
        )
    return rows


def _java(count):
    operations = (
        "SIGNATURE",
        "OVERLOADS",
        "PARAMETERS",
        "RETURN_TYPE",
        "GENERICS",
        "EXCEPTIONS",
        "DEPRECATION",
        "SINCE",
        "WORDING",
        "COMPILE",
        "RUN",
    )
    rows = []
    for index in range(count):
        operation = operations[index % len(operations)]
        target = f"sealedUnsupportedMethod{index:03d}"
        request = {
            "operation": operation,
            "receiver_type": "SealedUnknownType",
            "symbol": target,
            "version": "1.0.0-m33",
        }
        expected = (
            "NEEDS_NEW_CAPABILITY"
            if operation in {"COMPILE", "RUN"}
            else "INSUFFICIENT_EVIDENCE"
        )
        if index % 19 == 0 and operation not in {"COMPILE", "RUN"}:
            request["version"] = "version-mismatch"
            expected = "VERSION_MISMATCH"
        rows.append(_row("m33-java", operation, target, request, expected, index))
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
