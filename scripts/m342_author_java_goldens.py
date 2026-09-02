"""Author M-34.2 census/goldens with the independent JDK compiler helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ORACLE_VERSION = "m342.javac-oracle.v1"


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n", encoding="utf-8", newline="\n")


def run(java: Path, classes: Path, mode: str, sources: tuple[Path, ...]):
    command = [str(java), "-cp", str(classes), "JavaSemanticOracle", mode]
    command.extend(str(path.resolve()) for path in sources)
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return tuple(json.loads(line) for line in result.stdout.splitlines() if line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = tuple(sorted(args.corpus.rglob("*.java"), key=lambda path: path.name))
    with tempfile.TemporaryDirectory(prefix="m342-oracle-") as temporary:
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
        census_rows = run(args.java, classes, "census", sources)
        physical = tuple(
            sorted(
                (
                    {
                        "source_unit_id": row["source_unit_id"],
                        "document_bytes_hash": row["document_bytes_hash"],
                        "start_offset": row["start_offset"],
                        "end_offset": row["end_offset"],
                        "start_line": row["start_line"],
                        "end_line": row["end_line"],
                    }
                    for row in census_rows
                ),
                key=lambda row: (
                    row["source_unit_id"],
                    row["start_offset"],
                    row["end_offset"],
                ),
            )
        )
        if len(physical) != 600 or len({digest(row) for row in physical}) != 600:
            raise RuntimeError("M-34.2 physical target census must contain 600 targets")
        targets = tuple(
            {
                "target_id": f"m342.target.{index + 1:04d}",
                **row,
                "target_hash": digest(row),
            }
            for index, row in enumerate(physical)
        )
        census_body = {
            "schema_version": 1,
            "selection_phase": "PHYSICAL_PRE_CLASSIFICATION",
            "selection_rule": "all-methods-and-constructors-in-development-corpus",
            "targets": targets,
            "target_count": len(targets),
        }
        census = {**census_body, "census_hash": digest(census_body)}
        write(args.output / "target_census.json", census)

        oracle_rows = run(args.java, classes, "oracle", sources)
        oracle_by_physical = {
            (
                row["document_bytes_hash"],
                row["start_offset"],
                row["end_offset"],
            ): row
            for row in oracle_rows
        }
        helper_hash = hashlib.sha256(args.helper.read_bytes()).hexdigest()
        goldens = []
        for index, target in enumerate(targets):
            key = (
                target["document_bytes_hash"],
                target["start_offset"],
                target["end_offset"],
            )
            row = oracle_by_physical.get(key)
            if row is None:
                raise RuntimeError(
                    f"oracle omitted census target: {target['target_id']}"
                )
            body = {
                "golden_id": f"m342.golden.{index + 1:04d}",
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
                "erased_jvm_descriptor": row["erased_jvm_descriptor"],
                "expected_supported": row["expected_supported"],
                "unsupported_reason": row["unsupported_reason"],
                "negative_kind": None if row["expected_supported"] else "SEMANTIC",
            }
            goldens.append({**body, "golden_hash": digest(body)})
        source_rows = tuple(
            sorted(
                (
                    path.name,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in sources
            )
        )
        positive = sum(item["expected_supported"] for item in goldens)
        negative = len(goldens) - positive
        manifest_body = {
            "schema_version": 2,
            "authoring_implementation": ORACLE_VERSION,
            "sealed_before_proposals": True,
            "source_manifest_hash": digest(source_rows),
            "target_census_hash": census["census_hash"],
            "oracle_implementation_hash": helper_hash,
            "goldens": goldens,
            "positive_count": positive,
            "negative_count": negative,
            "semantic_negative_count": negative,
        }
        manifest = {**manifest_body, "manifest_hash": digest(manifest_body)}
        if (positive, negative) != (300, 300):
            raise RuntimeError(f"unexpected oracle labels: {(positive, negative)}")
        write(args.output / "semantic_goldens.json", manifest)

        seal_body = {
            "schema_version": 1,
            "source_manifest_hash": manifest["source_manifest_hash"],
            "target_census_hash": census["census_hash"],
            "golden_manifest_hash": manifest["manifest_hash"],
            "oracle_implementation_hash": helper_hash,
            "seal_authority_identity": "m342-pre-freeze-release-authority",
            "seal_authority_type": "HUMAN_RELEASE_AUTHORITY",
            "sealing_phase": "PRE_PROPOSAL",
            "sealing_ref": "7629cf0088803cdf7cf3f9816d0d76cd26dd5e7f",
        }
        write(
            args.output / "golden_seal_receipt.json",
            {**seal_body, "seal_receipt_hash": digest(seal_body)},
        )
        invocation = {
            "schema_version": 1,
            "helper_hash": helper_hash,
            "javac_version": subprocess.run(
                [str(args.javac), "-version"],
                check=True,
                capture_output=True,
                text=True,
            ).stderr.strip()
            or subprocess.run(
                [str(args.javac), "-version"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "compile_options": ["--release", "21", "-proc:none"],
            "oracle_options": ["--release", "21", "-proc:none", "-Xlint:none"],
            "source_count": len(sources),
            "census_count": len(census_rows),
            "oracle_count": len(oracle_rows),
        }
        write(
            args.output / "oracle_invocation_receipt.json",
            {**invocation, "receipt_hash": digest(invocation)},
        )


if __name__ == "__main__":
    main()
