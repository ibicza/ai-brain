"""Execute the sixteen mandatory M-33.5 freeze disclosure mutations."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    _git_tree,
    _under,
    verify_java_git_freeze_protocol,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    FinalArtifactRole,
    build_final_artifact_role_manifest,
    verify_role_aware_disclosure,
)


def _rehash(value):
    body = asdict(value)
    body.pop("manifest_hash")
    return replace(value, manifest_hash=content_hash(body))


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repository), *args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repository: Path, path: str, value: str, message: str) -> str:
    target = repository / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8", newline="\n")
    _git(repository, "add", path)
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def _git_mutations() -> dict[str, bool]:
    with tempfile.TemporaryDirectory(prefix="m335-freeze-mutations-") as temporary:
        repository = Path(temporary)
        _git(repository, "init", "-b", "main")
        _git(repository, "config", "user.email", "m335@example.invalid")
        _git(repository, "config", "user.name", "M335 Mutation")
        base = _commit(repository, "src/frozen.py", "base\n", "base")
        _git(repository, "switch", "-c", "excluded")
        excluded = _commit(repository, "outside.txt", "outside\n", "excluded")
        _git(repository, "switch", "main")
        f13 = _commit(
            repository,
            "scripts/frozen.py",
            "f13\n",
            "M-34.4 freeze oracle-free Java acquisition",
        )
        _commit(
            repository,
            "evaluation/m344_final_java/source_snapshots/A.java",
            "class A {}\n",
            "M-34.4 untouched real-Java evaluation",
        )
        e13 = _commit(
            repository,
            "runs/m344_fresh_java_freeze/report.json",
            "{}\n",
            "M-34.4 exact-SHA fresh-freeze evidence",
        )
        wrong_chain = verify_java_git_freeze_protocol(
            repository,
            base_sha=base,
            f13_sha=f13,
            h13_sha=f13,
            e13_sha=e13,
            excluded_m33_sha=excluded,
            branch="main",
        )
        _git(repository, "switch", "-c", "frozen-change", f13)
        changed_h = _commit(
            repository,
            "src/frozen.py",
            "changed\n",
            "M-34.4 untouched real-Java evaluation",
        )
        changed_e = _commit(
            repository,
            "runs/m344_fresh_java_freeze/report.json",
            "{}\n",
            "M-34.4 exact-SHA fresh-freeze evidence",
        )
        frozen_change = verify_java_git_freeze_protocol(
            repository,
            base_sha=base,
            f13_sha=f13,
            h13_sha=changed_h,
            e13_sha=changed_e,
            excluded_m33_sha=excluded,
            branch="frozen-change",
        )
        _git(repository, "switch", "--detach", e13)
        blob = _git(repository, "hash-object", "-w", "--stdin")
        _git(repository, "update-index", "--add", "--cacheinfo", f"120000,{blob},link")
        _git(repository, "commit", "-m", "symlink mutation")
        symlink_sha = _git(repository, "rev-parse", "HEAD")
        symlink_blocked = False
        try:
            _git_tree(str(repository), symlink_sha, ())
        except ValueError:
            symlink_blocked = True
        return {
            "symlink": symlink_blocked,
            "frozen_source_selector_changed_after_f": not frozen_change.passed,
            "h_e_parent_chain_changed": not wrong_chain.passed,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    zero = b'{"count":0,"status":"PASS"}\n'
    h = {
        "evaluation/m344_final_java/source_snapshots/A.java": b"class A {}\n",
        "evaluation/m344_final_java/source_acquisition_receipts.json": b'{"canonical":"CANONICAL_HASH"}\n',
        "evaluation/m344_final_java/selector_receipt.json": b'{"selected":"FINAL/PATH"}\n',
        "evaluation/m344_final_java/physical_census.json": b'{"target":"PHYSICAL_ID"}\n',
        "evaluation/m344_final_java/production_output.json": b'{"hash":"PRODUCTION_HASH"}\n',
        "evaluation/m344_final_java/oracle/semantic_goldens.json": b'{"hash":"GOLDEN_HASH"}\n',
        "evaluation/m344_final_java/evaluation_report.json": b'{"hash":"EVALUATOR_HASH"}\n',
        "evaluation/m344_final_java/outcome.json": b'{"decision":"FINAL_DECISION"}\n',
        "evaluation/m344_final_java/production_process_audit.json": zero,
    }
    manifest = build_final_artifact_role_manifest(h)
    results = {
        "final_source_bytes_copied": not verify_role_aware_disclosure(
            {
                "renamed/source.txt": h[
                    "evaluation/m344_final_java/source_snapshots/A.java"
                ]
            },
            h,
            manifest,
        ).passed,
    }
    tokens = {
        "canonical_source_hash_in_manifest": "CANONICAL_HASH",
        "selected_path_in_f_config": "FINAL/PATH",
        "physical_target_identity_leaked": "PHYSICAL_ID",
        "golden_hash_leaked": "GOLDEN_HASH",
        "production_output_hash_leaked": "PRODUCTION_HASH",
        "evaluator_output_leaked": "EVALUATOR_HASH",
        "final_decision_leaked": "FINAL_DECISION",
    }
    for name, token in tokens.items():
        report = verify_role_aware_disclosure(
            {f"f/{name}.json": f'{{"value":"{token}"}}\n'.encode()},
            h,
            manifest,
            protected_tokens=(token,),
        )
        results[name] = not report.passed
    source_binding = next(
        item
        for item in manifest.bindings
        if item.role is FinalArtifactRole.FINAL_SOURCE_BYTES
    )
    changed = replace(
        manifest,
        bindings=tuple(
            replace(item, role=FinalArtifactRole.PROCESS_AUDIT)
            if item == source_binding
            else item
            for item in manifest.bindings
        ),
    )
    for name, candidate in (
        ("role_changed_final_source_to_audit", _rehash(changed)),
        (
            "incomplete_role_manifest",
            _rehash(replace(manifest, bindings=manifest.bindings[:-1])),
        ),
        (
            "caller_weakens_protected_roles",
            _rehash(replace(manifest, protected_roles=manifest.protected_roles[:-1])),
        ),
    ):
        try:
            verify_role_aware_disclosure({}, h, candidate)
        except ValueError:
            results[name] = True
        else:
            results[name] = False
    results["path_prefix_confusion"] = not _under(
        "evaluation/m344_final_java_evil/source.java",
        ("evaluation/m344_final_java",),
    )
    try:
        build_final_artifact_role_manifest(
            {
                "evaluation/final/cafe\u0301.json": b"1",
                "evaluation/final/caf\u00e9.json": b"2",
            }
        )
    except ValueError:
        results["normalized_path_duplicate"] = True
    else:
        results["normalized_path_duplicate"] = False
    results.update(_git_mutations())
    ordered = tuple((name, results[name]) for name in sorted(results))
    body = {
        "schema_version": 1,
        "mutation_count": len(ordered),
        "blocked_count": sum(value for _name, value in ordered),
        "mutations": ordered,
        "neutral_audit_blob_reuse_pass": verify_role_aware_disclosure(
            {"f/zero.json": zero}, h, manifest
        ).passed,
    }
    if body["mutation_count"] != 16 or body["blocked_count"] != 16:
        raise AssertionError("not all sixteen M-33.5 freeze mutations were blocked")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
