"""Author the sealed M-34.3 semantic census with the independent JDK oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

ORACLE_VERSION = "m343.javac-semantic-proposal-oracle.v1"
STAMP_REF = "ed8cae0a8ad9d36530ae23ce9e07aae2615a9f48"


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n", encoding="utf-8", newline="\n")


def run_oracle(java, classes, corpus, sources, patch_java_base=None):
    arguments = [
        "-Dfile.encoding=UTF-8",
    ]
    if patch_java_base is not None:
        arguments.append(f"-Dm344.patchJavaBase={patch_java_base.resolve().as_posix()}")
    arguments.extend(
        [
            "-cp",
            classes.resolve().as_posix(),
            "JavaSemanticProposalOracle",
            "oracle",
            corpus.resolve().as_posix(),
        ]
    )
    arguments.extend(path.resolve().as_posix() for path in sources)
    # Java launcher argument files avoid the Windows CreateProcess command-line
    # limit while preserving the exact, explicitly ordered source list.
    with tempfile.TemporaryDirectory(prefix="m335-java-oracle-args-") as temporary:
        argument_file = Path(temporary) / "oracle.args"
        argument_file.write_text(
            "\n".join(_java_argument(value) for value in arguments) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        completed = subprocess.run(
            [str(java), f"@{argument_file.resolve().as_posix()}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    return tuple(json.loads(line) for line in completed.stdout.splitlines() if line)


def _java_argument(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def object_type(row):
    source = row["source_return_type"]
    resolved = row["resolved_return_type"]
    if row["member_kind"] == "constructor":
        kind, identity = "ENTITY", row["receiver_source_identity"]
    elif source.endswith(("[]", "...")) or (resolved or "").endswith("[]"):
        kind, identity = "ENTITY", resolved or source
    else:
        source_base = base_type(source)
        resolved_base = base_type(resolved or "")
        if "void" in {source_base, resolved_base}:
            kind, identity = "VOID", None
        elif "boolean" in {source_base, resolved_base}:
            kind, identity = "BOOLEAN", None
        elif source_base in {
            "byte",
            "short",
            "int",
            "long",
            "char",
        } or resolved_base in {"byte", "short", "int", "long", "char"}:
            kind, identity = "INTEGER", None
        elif source_base in {"float", "double"} or resolved_base in {"float", "double"}:
            kind, identity = "DECIMAL", None
        elif source_base in {"String", "CharSequence"} or resolved_base in {
            "java.lang.String",
            "java.lang.CharSequence",
        }:
            kind, identity = "STRING", None
        else:
            kind, identity = "ENTITY", resolved or source
    return (
        {
            "kind": kind,
            "entity_type": {"entity_type_id": identity}
            if identity is not None
            else None,
            "quantity_type": None,
        },
        kind,
        identity,
    )


def claim_payload(row):
    value_type, _kind, _identity = object_type(row)
    resolved_parameters = [
        value if value is not None else f"UNRESOLVED:{source}"
        for source, value in zip(
            row["source_parameter_types"], row["resolved_parameter_types"], strict=True
        )
    ]
    resolved_return = (
        row["resolved_return_type"] or f"UNRESOLVED:{row['source_return_type']}"
    )
    resolved_exceptions = [
        value if value is not None else f"UNRESOLVED:{source}"
        for source, value in zip(
            row["declared_exception_source_types"],
            row["resolved_declared_exception_types"],
            strict=True,
        )
    ]
    first_bounds = [
        value
        if value is not None
        else f"UNRESOLVED:{row['resolution_source_bounds'][index][0]}"
        for index, value in enumerate(row["first_bound_erasures"])
    ]
    return {
        "subject_type": {"entity_type_id": row["receiver_source_identity"]},
        "predicate_id": "<init>"
        if row["member_kind"] == "constructor"
        else row["member_name"],
        "object_type": value_type,
        "qualifier_ids": [],
        "receiver_type": row["receiver_source_identity"],
        "parameters": [
            list(item)
            for item in zip(
                row["parameter_names"], row["source_parameter_types"], strict=True
            )
        ],
        "return_type": row["source_return_type"],
        "generic_constraints": [
            f"{name} extends {' & '.join(bounds)}"
            for name, bounds in zip(
                row["method_type_parameters"], row["intersection_bounds"], strict=True
            )
            if bounds
        ],
        "preconditions": [],
        "postconditions": [],
        "declared_exceptions": row["declared_exception_source_types"],
        "deprecated_since": row["deprecated_since"],
        "examples": [],
        "java_callable_kind": "CONSTRUCTOR"
        if row["member_kind"] == "constructor"
        else "METHOD",
        "resolved_parameter_types": resolved_parameters,
        "parameter_array_dimensions": row["parameter_array_dimensions"],
        "parameter_varargs": row["parameter_varargs"],
        "resolved_return_type": resolved_return,
        "return_array_dimensions": row["return_array_dimensions"],
        "method_type_parameters": row["method_type_parameters"],
        "intersection_bounds": row["intersection_bounds"],
        "first_bound_erasures": first_bounds,
        "resolved_declared_exceptions": resolved_exceptions,
        "modifiers": row["modifiers"],
        "accessibility": row["accessibility"],
        "enclosing_type_accessibility": row["enclosing_type_accessibility"],
        "module_name": row["module_name"],
        "package_exported": row["package_exported"],
    }


def type_resolution_hash(row):
    values = []
    for outer, (sources, resolved) in enumerate(
        zip(
            row["resolution_source_bounds"],
            row["resolved_intersection_bounds"],
            strict=True,
        )
    ):
        for inner, (source, target) in enumerate(zip(sources, resolved, strict=True)):
            values.append(
                (
                    f"type_parameters[{outer}].bounds[{inner}]",
                    source,
                    target,
                    dimensions(source),
                )
            )
    for index, (source, target) in enumerate(
        zip(row["source_parameter_types"], row["resolved_parameter_types"], strict=True)
    ):
        values.append((f"parameters[{index}].type", source, target, dimensions(source)))
    values.append(
        (
            "return_type",
            row["source_return_type"],
            row["resolved_return_type"],
            dimensions(row["source_return_type"]),
        )
    )
    for index, (source, target) in enumerate(
        zip(
            row["declared_exception_source_types"],
            row["resolved_declared_exception_types"],
            strict=True,
        )
    ):
        values.append(
            (f"declared_exceptions[{index}]", source, target, dimensions(source))
        )
    values.append(
        (
            "receiver_type",
            row["receiver_source_identity"],
            row["receiver_source_identity"],
            0,
        )
    )
    return digest(values)


def field_manifest_hash(payload):
    return digest(sorted(flatten(payload).items()))


def flatten(value, prefix="content"):
    result = {}
    if isinstance(value, dict):
        for key in sorted(value):
            result.update(flatten(value[key], f"{prefix}.{key}"))
    elif isinstance(value, list):
        if not value:
            result[prefix] = []
        for index, item in enumerate(value):
            result.update(flatten(item, f"{prefix}[{index}]"))
    else:
        result[prefix] = value
    return result


def diagnostics(rows, targets, corpus, *, scope_v2=False):
    result = []
    by_unit = {}
    for target in targets:
        by_unit.setdefault(target["source_unit_id"], []).append(target)
    for row in (item for item in rows if item["record_type"] == "diagnostic"):
        candidates = by_unit.get(row["source_unit_id"], [])
        overlapping = [
            item
            for item in candidates
            if row["start_offset"] < item["end_offset"]
            and row["end_offset"] > item["start_offset"]
        ]
        affected = overlapping or [
            item for item in candidates if not item["oracle_supported"]
        ]
        applicability = "ENCLOSING_TYPE_BLOCKING" if scope_v2 else "UNIT_HEADER"
        if overlapping:
            raw = (corpus / row["source_unit_id"]).read_bytes()
            body_start = raw.find(
                b"{", overlapping[0]["start_offset"], overlapping[0]["end_offset"]
            )
            if scope_v2:
                applicability = (
                    "BODY_ONLY"
                    if body_start >= 0 and row["start_offset"] > body_start
                    else "DECLARATION_HEADER_BLOCKING"
                )
            else:
                applicability = (
                    "BODY"
                    if body_start >= 0 and row["start_offset"] > body_start
                    else "HEADER"
                )
        elif scope_v2 and not affected:
            applicability = "AMBIENT_FILE"
        body = {
            "diagnostic_code": row["diagnostic_code"],
            "diagnostic_kind": row["diagnostic_kind"],
            "source_unit_id": row["source_unit_id"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "line": row["line"],
            "column": row["column"],
            "target_ids": [item["target_id"] for item in affected],
            "normalized_category": row["normalized_category"],
            "applicability": applicability,
            "trust_relevant": applicability
            not in {"BODY", "BODY_ONLY", "AMBIENT_FILE", "UNRELATED_DECLARATION"},
        }
        result.append({**body, "receipt_hash": digest(body)})
    return sorted(
        result,
        key=lambda item: (
            item["source_unit_id"],
            item["start_offset"],
            item["diagnostic_code"],
        ),
    )


def base_type(value):
    value = value.removesuffix("...")
    while value.endswith("[]"):
        value = value[:-2]
    depth, result = 0, []
    for character in value:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            result.append(character)
    return "".join(result).strip()


def dimensions(value):
    count = 1 if value.endswith("...") else 0
    value = value.removesuffix("...")
    while value.endswith("[]"):
        count += 1
        value = value[:-2]
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parser-common-hash", required=True)
    parser.add_argument("--evidence-policy-hash", required=True)
    parser.add_argument("--disjoint-root", type=Path, action="append", default=[])
    parser.add_argument("--patch-java-base", type=Path)
    parser.add_argument("--authority-id", default="m343-semantic-pre-freeze-authority")
    parser.add_argument("--sealing-ref", default=STAMP_REF)
    parser.add_argument("--authority-purpose", default="development-only-pre-freeze")
    parser.add_argument("--config-id", default="m343.external-java-trust-evaluation.v1")
    parser.add_argument("--real-prefix", action="append", default=[])
    parser.add_argument("--diagnostic-scope-v2", action="store_true")
    parser.add_argument(
        "--disjoint-hash-manifest", type=Path, action="append", default=[]
    )
    args = parser.parse_args()
    sources = tuple(
        sorted(
            args.corpus.rglob("*.java"),
            key=lambda item: item.relative_to(args.corpus).as_posix(),
        )
    )
    with tempfile.TemporaryDirectory(prefix="m343-oracle-") as temporary:
        classes = Path(temporary)
        compile_command = [
            str(args.javac),
            "--release",
            "21",
            "-proc:none",
            "-d",
            str(classes),
            str(args.helper),
        ]
        subprocess.run(compile_command, check=True)
        rows = run_oracle(
            args.java, classes, args.corpus, sources, args.patch_java_base
        )
    proposal_rows = tuple(item for item in rows if item["record_type"] == "proposal")
    physical = sorted(
        proposal_rows,
        key=lambda item: (
            item["source_unit_id"],
            item["start_offset"],
            item["end_offset"],
        ),
    )
    targets = []
    for index, row in enumerate(physical):
        target = {
            "target_id": f"m343.target.{index + 1:05d}",
            "source_unit_id": row["source_unit_id"],
            "document_bytes_hash": row["document_bytes_hash"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "oracle_supported": row["expected_supported"],
        }
        target["target_hash"] = digest(target)
        targets.append(target)
    census_body = {
        "schema_version": 2,
        "selection_phase": "PHYSICAL_PRE_CLASSIFICATION",
        "selection_rule": "all-callables-by-relative-path-document-hash-byte-span",
        "targets": [
            {key: value for key, value in item.items() if key != "oracle_supported"}
            for item in targets
        ],
        "target_count": len(targets),
    }
    census = {**census_body, "census_hash": digest(census_body)}
    diagnostic_rows = diagnostics(
        rows, targets, args.corpus, scope_v2=args.diagnostic_scope_v2
    )
    diagnostic_by_target = {}
    for item in diagnostic_rows:
        if item["trust_relevant"]:
            for target_id in item["target_ids"]:
                diagnostic_by_target.setdefault(target_id, []).append(item)
    helper_hash = bytes_digest(args.helper.read_bytes())
    goldens = []
    semantics_values = []
    for index, (target, row) in enumerate(zip(targets, physical, strict=True)):
        payload = claim_payload(row)
        _value_type, kind, identity = object_type(row)
        target_diagnostics = diagnostic_by_target.get(target["target_id"], [])
        supported = row["expected_supported"] and not target_diagnostics
        blocker = (
            target_diagnostics[0]["normalized_category"]
            if target_diagnostics
            else (None if supported else "ORACLE_UNSUPPORTED_TYPE")
        )
        semantics_body = {
            "target_id": target["target_id"],
            "receiver_source_identity": row["receiver_source_identity"],
            "receiver_binary_identity": row["receiver_binary_identity"],
            "parameter_names": row["parameter_names"],
            "source_parameter_types": row["source_parameter_types"],
            "resolved_parameter_types": [
                value if value is not None else f"UNRESOLVED:{source}"
                for source, value in zip(
                    row["source_parameter_types"],
                    row["resolved_parameter_types"],
                    strict=True,
                )
            ],
            "parameter_varargs": row["parameter_varargs"],
            "parameter_array_dimensions": row["parameter_array_dimensions"],
            "source_return_type": row["source_return_type"],
            "resolved_return_type": row["resolved_return_type"]
            or f"UNRESOLVED:{row['source_return_type']}",
            "return_array_dimensions": row["return_array_dimensions"],
            "method_type_parameters": row["method_type_parameters"],
            "intersection_bounds": row["intersection_bounds"],
            "first_bound_erasures": payload["first_bound_erasures"],
            "declared_exception_source_types": row["declared_exception_source_types"],
            "resolved_declared_exception_types": payload[
                "resolved_declared_exceptions"
            ],
            "modifiers": row["modifiers"],
            "accessibility": row["accessibility"],
            "enclosing_type_accessibility": row["enclosing_type_accessibility"],
            "module_name": row["module_name"],
            "package_exported": row["package_exported"],
            "deprecated_since": row["deprecated_since"],
            "expected_knowledge_kind": "CLAIM_SCHEMA",
            "expected_epistemic_character": "NORMATIVE",
            "expected_subject_type": row["receiver_source_identity"],
            "expected_object_type_kind": kind,
            "expected_object_type_identity": identity,
            "expected_claim_payload": canonical(payload),
            "expected_semantic_content_hash": digest(payload),
            "complete_type_resolution_manifest_hash": type_resolution_hash(row),
            "complete_proposal_field_manifest_hash": field_manifest_hash(payload),
            "expected_supported": supported,
            "expected_blocker_reason": blocker,
        }
        semantics = {**semantics_body, "semantic_hash": digest(semantics_body)}
        semantics_values.append(semantics)
        golden_body = {
            "golden_id": f"m343.golden.{index + 1:05d}",
            "source_unit_id": row["source_unit_id"],
            "document_bytes_hash": row["document_bytes_hash"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "package_name": row["package_name"],
            "top_level_type_name": row["top_level_type_name"],
            "nested_type_path": row["nested_type_path"],
            "member_kind": row["member_kind"],
            "member_name": row["member_name"],
            "canonical_source_signature": row["canonical_source_signature"],
            "erased_jvm_descriptor": row["erased_jvm_descriptor"] or "UNRESOLVED",
            "expected_supported": supported,
            "unsupported_reason": blocker,
            "negative_kind": None if supported else "SEMANTIC",
            "expected_semantics": semantics,
            "diagnostic_receipt_hashes": [
                item["receipt_hash"] for item in target_diagnostics
            ],
        }
        goldens.append({**golden_body, "golden_hash": digest(golden_body)})
    source_rows = sorted(
        (path.relative_to(args.corpus).as_posix(), bytes_digest(path.read_bytes()))
        for path in sources
    )
    positive = sum(item["expected_supported"] for item in goldens)
    negative = len(goldens) - positive
    diagnostic_counts = sorted(
        Counter(item["normalized_category"] for item in diagnostic_rows).items()
    )
    manifest_body = {
        "schema_version": 3,
        "authoring_implementation": ORACLE_VERSION,
        "sealed_before_proposals": True,
        "source_manifest_hash": digest(source_rows),
        "target_census_hash": census["census_hash"],
        "oracle_implementation_hash": helper_hash,
        "goldens": goldens,
        "positive_count": positive,
        "negative_count": negative,
        "semantic_negative_count": negative,
        "semantic_manifest_hash": digest(semantics_values),
        "diagnostic_manifest_hash": digest(diagnostic_rows),
        "diagnostics": diagnostic_rows,
        "diagnostic_counts": diagnostic_counts,
    }
    manifest = {**manifest_body, "manifest_hash": digest(manifest_body)}
    seal_body = {
        "schema_version": 2,
        "source_manifest_hash": manifest["source_manifest_hash"],
        "target_census_hash": census["census_hash"],
        "golden_manifest_hash": manifest["manifest_hash"],
        "oracle_implementation_hash": helper_hash,
        "seal_authority_identity": args.authority_id,
        "seal_authority_type": "HUMAN_RELEASE_AUTHORITY",
        "sealing_phase": "PRE_PROPOSAL",
        "sealing_ref": args.sealing_ref,
        "semantic_manifest_hash": manifest["semantic_manifest_hash"],
        "diagnostic_manifest_hash": manifest["diagnostic_manifest_hash"],
    }
    seal = {**seal_body, "seal_receipt_hash": digest(seal_body)}
    authority_root = digest(
        {
            "authority": args.authority_id,
            "base": args.sealing_ref,
            "purpose": args.authority_purpose,
        }
    )
    config_body = {
        "schema_version": 2,
        "config_id": args.config_id,
        "expected_golden_seal_hash": seal["seal_receipt_hash"],
        "expected_parser_common_artifact_hash": args.parser_common_hash,
        "expected_evidence_policy_hash": args.evidence_policy_hash,
        "expected_source_manifest_hash": manifest["source_manifest_hash"],
        "expected_target_census_hash": census["census_hash"],
        "expected_oracle_implementation_hash": helper_hash,
        "expected_sealing_phase": "PRE_PROPOSAL",
        "expected_sealing_ref": args.sealing_ref,
        "expected_authority_identity": args.authority_id,
        "expected_authority_type": "HUMAN_RELEASE_AUTHORITY",
        "expected_semantic_manifest_hash": manifest["semantic_manifest_hash"],
        "expected_diagnostic_manifest_hash": manifest["diagnostic_manifest_hash"],
        "authority_root_hash": authority_root,
    }
    config = {**config_body, "config_hash": digest(config_body)}
    previous_hashes = {
        bytes_digest(path.read_bytes())
        for root in args.disjoint_root
        for path in root.rglob("*.java")
    }
    for path in args.disjoint_hash_manifest:
        hash_manifest = json.loads(path.read_text(encoding="utf-8"))
        values = hash_manifest.get("snapshot_bytes_hashes")
        if not isinstance(values, list) or not all(
            isinstance(value, str) and len(value) == 64 for value in values
        ):
            raise ValueError(f"invalid disjoint source-hash manifest: {path}")
        previous_hashes.update(values)
    current_hashes = {value for _, value in source_rows}
    overloads = Counter(
        (row["receiver_source_identity"], row["member_name"])
        for row in proposal_rows
        if row["member_kind"] == "method"
    )
    real_prefixes = tuple(tuple(Path(item).parts) for item in args.real_prefix)
    real_sources = tuple(
        path
        for path in sources
        if (
            any(
                path.relative_to(args.corpus).parts[: len(prefix)] == prefix
                for prefix in real_prefixes
            )
            if real_prefixes
            else path.relative_to(args.corpus).parts[:2] == ("real", "openjdk-25")
        )
    )
    corpus_body = {
        "schema_version": 1,
        "source_file_count": len(sources),
        "real_source_file_count": len(real_sources),
        "synthetic_source_file_count": len(sources) - len(real_sources),
        "package_count": len({row["package_name"] for row in proposal_rows}),
        "pinned_library_roots": args.real_prefix
        or [
            "real/openjdk-25/java.base",
            "real/openjdk-25/java.compiler",
            "real/openjdk-25/java.desktop",
        ],
        "callable_count": len(proposal_rows),
        "positive_count": positive,
        "negative_count": negative,
        "semantic_negative_count": negative,
        "legal_overload_group_count": sum(value > 1 for value in overloads.values()),
        "constructor_count": sum(
            row["member_kind"] == "constructor" for row in proposal_rows
        ),
        "generic_method_count": sum(
            bool(row["method_type_parameters"]) for row in proposal_rows
        ),
        "intersection_bound_method_count": sum(
            any(len(value) > 1 for value in row["intersection_bounds"])
            for row in proposal_rows
        ),
        "throws_declaration_count": sum(
            bool(row["declared_exception_source_types"]) for row in proposal_rows
        ),
        "nested_member_case_count": sum(
            bool(row["nested_type_path"]) for row in proposal_rows
        ),
        "crlf_file_count": sum(b"\r\n" in path.read_bytes() for path in sources),
        "cr_only_file_count": sum(
            b"\r" in path.read_bytes() and b"\r\n" not in path.read_bytes()
            for path in sources
        ),
        "no_final_newline_file_count": sum(
            not path.read_bytes().endswith((b"\n", b"\r")) for path in sources
        ),
        "duplicate_basename_count": len(sources) - len({path.name for path in sources}),
        "prior_source_hash_intersection_count": len(current_hashes & previous_hashes),
        "source_manifest_hash": manifest["source_manifest_hash"],
    }
    invocation_body = {
        "schema_version": 1,
        "helper_hash": helper_hash,
        "javac_version": subprocess.run(
            [str(args.javac), "-version"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "compile_argv_policy": ["--release", "21", "-proc:none"],
        "oracle_argv_policy": [
            "--release",
            "21",
            "-proc:none",
            "-Xlint:none",
            *(
                ["--patch-module", "java.base=<sealed-source-root>"]
                if args.patch_java_base
                else []
            ),
        ],
        "source_execution_count": 0,
        "annotation_processor_invocation_count": 0,
        "source_count": len(sources),
        "proposal_count": len(proposal_rows),
        "diagnostic_count": len(diagnostic_rows),
    }
    write(args.output / "target_census.json", census)
    write(args.output / "semantic_goldens.json", manifest)
    write(args.output / "golden_seal_receipt.json", seal)
    write(args.output / "evaluation_config.json", config)
    write(args.output / "authority_root.json", {"authority_root_hash": authority_root})
    write(
        args.output / "corpus_manifest.json",
        {**corpus_body, "manifest_hash": digest(corpus_body)},
    )
    write(
        args.output / "oracle_invocation_receipt.json",
        {**invocation_body, "receipt_hash": digest(invocation_body)},
    )


if __name__ == "__main__":
    main()
