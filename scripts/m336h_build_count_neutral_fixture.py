"""Build an original twelve-file Java route-shape rehearsal outside Git."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_production_compiler import (
    build_java_production_compilation_probe,
    run_java_production_compilation_probe,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336e_identity import (
    build_source_entry_binding,
    build_source_entry_binding_manifest,
    build_source_entry_id,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    build_selectable_source_census,
    build_selectable_source_decision,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    build_java_compilation_closure_manifest,
    prove_java_compilation_closure_feasibility,
)
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.maven_provenance import canonical_source_bytes
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _sources() -> dict[str, bytes]:
    rows = {
        "alpha/com/example/alpha/AlphaSupport.java": """
package com.example.alpha;
final class AlphaSupport { int value; }
""",
        "alpha/com/example/alpha/AlphaApi.java": """
package com.example.alpha;
public final class AlphaApi {
    public int size(AlphaSupport value) { return value.value; }
}
""",
        "alpha/com/example/alpha/AlphaOne.java": """
package com.example.alpha;
public final class AlphaOne { public int one() { return 1; } }
""",
        "alpha/com/example/alpha/AlphaTwo.java": """
package com.example.alpha;
public final class AlphaTwo { public int two() { return 2; } }
""",
        "beta/com/example/beta/BetaOne.java": """
package com.example.beta;
public final class BetaOne { public int one() { return 1; } }
""",
        "beta/com/example/beta/BetaTwo.java": """
package com.example.beta;
public final class BetaTwo { public int two() { return 2; } }
""",
        "beta/com/example/beta/BetaThree.java": """
package com.example.beta;
public final class BetaThree { public int three() { return 3; } }
""",
        "beta/com/example/beta/BetaBroken.java": """
package com.example.beta;
public final class BetaBroken { public MissingType broken() { return null; } }
""",
        "gamma/com/example/gamma/GammaOne.java": """
package com.example.gamma;
public final class GammaOne { public int one() { return 1; } }
""",
        "gamma/com/example/gamma/GammaTwo.java": """
package com.example.gamma;
public final class GammaTwo { public int two() { return 2; } }
""",
        "gamma/com/example/gamma/GammaThree.java": """
package com.example.gamma;
public final class GammaThree { public int three() { return 3; } }
""",
        "gamma/com/example/gamma/GammaFour.java": """
package com.example.gamma;
public final class GammaFour { public int four() { return 4; } }
""",
    }
    return {path: (text.strip() + "\n").encode("utf-8") for path, text in rows.items()}


def _document_identity(selected_path: str, raw_hash: str) -> str:
    body = {
        "schema_version": 2,
        "bundle_id": "m336-final-java",
        "relative_path": selected_path,
        "bytes_hash": raw_hash,
    }
    return f"m336-final-java.document.{content_hash(body)[:32]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336H count-neutral fixture output must be fresh")
    root = args.output
    vault = root / "private_sealed_vault"
    inputs = root / "inputs"
    vault.mkdir(parents=True)
    inputs.mkdir()
    source_rows = _sources()
    for relative, raw in source_rows.items():
        path = vault.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    bindings = []
    identities = {}
    for selected_path, raw in sorted(source_rows.items()):
        family, _separator, archive_path = selected_path.partition("/")
        raw_hash = bytes_hash(raw)
        identity = build_source_entry_id(
            candidate_family_id=family,
            source_jar_sha256=content_hash(("M336H_ORIGINAL_FIXTURE", family)),
            archive_relative_path=archive_path,
            raw_source_sha256=raw_hash,
            canonical_source_sha256=bytes_hash(canonical_source_bytes(raw)),
        )
        identities[selected_path] = identity
        bindings.append(
            build_source_entry_binding(
                source_entry_id=identity,
                archive_path=archive_path,
                scm_path=archive_path,
                vault_path=selected_path,
                selected_path=selected_path,
                production_document_identity=_document_identity(
                    selected_path, raw_hash
                ),
            )
        )
    binding_manifest = build_source_entry_binding_manifest(bindings)
    with tempfile.TemporaryDirectory(prefix="m336h-neutral-build-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        source_paths = tuple(
            sorted(
                (path for path in vault.rglob("*.java")),
                key=lambda path: path.relative_to(vault).as_posix(),
            )
        )
        bundle = ingest_bundle(
            source_paths,
            bundle_id="m336h-count-neutral-fixture",
            domain_tags=("java-api",),
            imported_at="1970-01-01T00:00:00Z",
            source_root=vault,
            store=store,
        )
        source_index = index_java_bundle(bundle, store)
        declarations_by_unit = {
            unit: tuple(
                item
                for item in source_index.declarations
                if item.source_unit_id == unit
            )
            for unit in source_rows
        }
        decisions = []
        support_path = "alpha/com/example/alpha/AlphaSupport.java"
        for selected_path, identity in sorted(identities.items()):
            rows = declarations_by_unit[selected_path]
            callables = tuple(
                item for item in rows if item.member_kind in {"method", "constructor"}
            )
            supported = tuple(item for item in callables if item.supported)
            is_support = selected_path == support_path
            decisions.append(
                build_selectable_source_decision(
                    source_entry_id=identity,
                    candidate_root=identity.candidate_family_id,
                    canonical_path=identity.canonical_archive_relative_path,
                    analysis_eligible=True,
                    publication_allowed=True,
                    source_use_receipt_valid=True,
                    scoped_license_resolved=True,
                    scm_correspondence_complete=True,
                    parser_status="PASS",
                    declaration_count=len(rows),
                    callable_declaration_count=0 if is_support else len(callables),
                    supported_callable_declaration_count=(
                        0 if is_support else len(supported)
                    ),
                    construct_classes=()
                    if is_support
                    else tuple(item.member_kind for item in callables),
                    evidence_policy_path_declared=True,
                )
            )
        census = build_selectable_source_census(decisions)
        source_entry_ids = {
            path: identity.identity_hash for path, identity in identities.items()
        }
        probe = build_java_production_compilation_probe(args.javac.resolve(strict=True))
        compiler_report = run_java_production_compilation_probe(
            bundle=bundle,
            store=store,
            source_index=source_index,
            probe=probe,
            javac_executable=args.javac,
            source_entry_ids=source_entry_ids,
        )
        closure = build_java_compilation_closure_manifest(
            source_index=source_index,
            compiler_report=compiler_report,
            source_entry_ids=source_entry_ids,
        )
        proof = prove_java_compilation_closure_feasibility(
            closure,
            census,
            target_file_count=len(source_rows),
            minimum_root_count=3,
            maximum_files_per_root=5,
            construct_quotas=(("method", 1),),
            trust_capacity_target=1,
        )
    if not proof.hard_requirements_satisfied:
        raise ValueError(
            f"M336H original fixture is infeasible: {proof.failure_reasons}"
        )
    if support_path not in proof.witness_source_units:
        raise ValueError("M336H original fixture did not exercise closure support")
    report_body = {
        "schema_version": 1,
        "fixture_id": "m336h.original-count-neutral-java.v1",
        "source_count": len(source_rows),
    }
    summary_body = {
        "schema_version": 1,
        "fixture_id": "m336h.original-count-neutral-java.v1",
        "target_file_count": proof.target_file_count,
        "minimum_root_count": proof.minimum_root_count,
        "maximum_files_per_root": proof.maximum_files_per_root,
        "status": "PASS",
    }
    write_canonical_json(
        inputs / "source_entry_binding_manifest.json", binding_manifest
    )
    write_canonical_json(inputs / "selectability_census.json", census)
    write_canonical_json(inputs / "compilation_closure_manifest.json", closure)
    write_canonical_json(inputs / "compilation_closure_feasibility.json", proof)
    write_canonical_json(inputs / "compiler_probe.json", probe)
    write_canonical_json(inputs / "compiler_report.json", compiler_report)
    write_canonical_json(
        inputs / "candidate_qualification.json",
        {**report_body, "report_hash": content_hash(report_body)},
    )
    write_canonical_json(
        inputs / "qualification_summary.json",
        {**summary_body, "summary_hash": content_hash(summary_body)},
    )
    receipt_body = {
        "schema_version": 1,
        "fixture_id": "m336h.original-count-neutral-java.v1",
        "selected_target_count": proof.target_file_count,
        "minimum_selected_roots": proof.minimum_root_count,
        "maximum_files_per_root": proof.maximum_files_per_root,
        "closure_support_required": True,
        "compiler_diagnostic_count": compiler_report.diagnostic_count,
        "network_access_count": 0,
        "status": "PASS",
    }
    write_canonical_json(
        inputs / "fixture_receipt.json",
        {**receipt_body, "receipt_hash": content_hash(receipt_body)},
    )


if __name__ == "__main__":
    main()
