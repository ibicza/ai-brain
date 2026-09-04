"""Exact occurrence-level mapping of the immutable H17 disclosure defect."""

from __future__ import annotations

import json
import subprocess
import types
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.final_artifact_contract import (
    FINAL_ARTIFACT_CONTRACT_REGISTRY,
)

H17_SHA = "1a05ccfa0bad25a79e388dab7c6672fc308cb890"
E17_SHA = "1541805f9cd6c19ff9c372afeefbd41148217736"
EXPECTED_OCCURRENCE_COUNT = 36


@dataclass(frozen=True)
class H17ProtectedFieldOccurrenceMapping:
    h17_artifact_path: str
    json_pointer: str
    field_name: str
    value_type: str
    old_artifact_role: str
    old_classifier_result: str
    current_artifact_type: str
    current_artifact_role: str
    current_field_class: str
    current_mandatory_disclosure_claim: str | None
    mapping_reason: str
    mapping_receipt_hash: str


@dataclass(frozen=True)
class H17OccurrenceMappingReport:
    schema_version: int
    h17_sha: str
    e17_sha: str
    historical_occurrence_count: int
    mapped_occurrence_count: int
    unmapped_occurrence_count: int
    rows: tuple[H17ProtectedFieldOccurrenceMapping, ...]
    report_hash: str


def build_h17_occurrence_mapping(project: Path) -> H17OccurrenceMappingReport:
    project = project.resolve(strict=True)
    old = _load_old_policy(project)
    paths = _lines(project, "diff-tree", "--no-commit-id", "--name-only", "-r", H17_SHA)
    known = []
    values: dict[str, bytes] = {}
    roles = {}
    for path in sorted(paths):
        raw = _git_bytes(project, f"{H17_SHA}:{path}")
        try:
            role = old.classify_final_artifact_role(path)
        except ValueError:
            continue
        known.append(path)
        values[path] = raw
        roles[path] = role
    manifest = old.build_final_artifact_role_manifest(tuple(known))
    old_claims = old.extract_disclosure_claims(values, manifest)
    claimed_paths = {(item.source_path, item.field_path) for item in old_claims}
    rows = []
    for path in sorted(known):
        if path.endswith(".java") or roles[path] not in old.PROTECTED_FINAL_ROLES:
            continue
        try:
            value = json.loads(values[path].decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        for pointer, field_path, field_name, leaf in _protected_occurrences(
            value, old._PROTECTED_FIELD_NAMES
        ):
            if any(
                claim_path == path and claim_field.startswith(field_path)
                for claim_path, claim_field in claimed_paths
            ):
                continue
            contract = FINAL_ARTIFACT_CONTRACT_REGISTRY.match(path)
            fields = {item.field_name: item for item in contract.field_contracts}
            if field_name not in fields:
                raise ValueError(
                    f"current field contract omitted H17 field: {field_name}"
                )
            field = fields[field_name]
            reason = (
                "CURRENT_CONTRACT_SECRET_WITH_EXPLICIT_MANDATORY_CLAIM"
                if field.mandatory_disclosure_claim
                else f"CURRENT_CONTRACT_EXPLICIT_{field.field_class.value}_CLASSIFICATION"
            )
            body = {
                "h17_artifact_path": path,
                "json_pointer": pointer,
                "field_name": field_name,
                "value_type": _json_type(leaf),
                "old_artifact_role": roles[path].value,
                "old_classifier_result": "EXTRA_PROTECTED_FIELD_UNCLAIMED",
                "current_artifact_type": contract.artifact_type,
                "current_artifact_role": contract.role.value,
                "current_field_class": field.field_class.value,
                "current_mandatory_disclosure_claim": field.mandatory_disclosure_claim,
                "mapping_reason": reason,
            }
            rows.append(
                H17ProtectedFieldOccurrenceMapping(
                    **body, mapping_receipt_hash=content_hash(body)
                )
            )
    ordered = tuple(
        sorted(rows, key=lambda item: (item.h17_artifact_path, item.json_pointer))
    )
    if len(ordered) != EXPECTED_OCCURRENCE_COUNT:
        raise ValueError(
            f"historical H17 occurrence denominator changed: {len(ordered)}"
        )
    body = {
        "schema_version": 1,
        "h17_sha": H17_SHA,
        "e17_sha": E17_SHA,
        "historical_occurrence_count": EXPECTED_OCCURRENCE_COUNT,
        "mapped_occurrence_count": len(ordered),
        "unmapped_occurrence_count": EXPECTED_OCCURRENCE_COUNT - len(ordered),
        "rows": ordered,
    }
    return H17OccurrenceMappingReport(**body, report_hash=content_hash(body))


def _load_old_policy(project: Path):
    source = _git_bytes(
        project,
        f"{E17_SHA}:src/ai_brain/stage3/acquisition/java_freeze_roles.py",
    ).decode("utf-8", errors="strict")
    module = types.ModuleType("m336d_immutable_e17_java_freeze_roles")
    module.__file__ = f"git:{E17_SHA}:java_freeze_roles.py"
    import sys

    sys.modules[module.__name__] = module
    # The executed bytes are read from the exact immutable E17 Git object above.
    exec(compile(source, module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


def _protected_occurrences(value, protected_names, pointer="", field_path="$"):
    if isinstance(value, dict):
        for key, child in sorted(value.items()):
            child_pointer = f"{pointer}/{_pointer_token(key)}"
            child_field = f"{field_path}.{key}"
            if key in protected_names:
                yield child_pointer, child_field, key, child
            yield from _protected_occurrences(
                child, protected_names, child_pointer, child_field
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _protected_occurrences(
                child, protected_names, f"{pointer}/{index}", f"{field_path}[{index}]"
            )


def _json_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError("unsupported JSON value")


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _lines(project: Path, *args: str) -> tuple[str, ...]:
    return tuple(
        subprocess.run(
            ("git", *args),
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines()
    )


def _git_bytes(project: Path, object_name: str) -> bytes:
    return subprocess.run(
        ("git", "show", object_name),
        cwd=project,
        check=True,
        capture_output=True,
    ).stdout
