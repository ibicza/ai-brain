from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_evidence import (
    M336J_Q25_SUBJECT,
    M336J_QUALIFICATION_REQUIRED_FILES,
    build_m336j_q25_staging,
    q25_staging_receipt_from_dict,
    qualification_input_tree_hash,
    verify_m336j_post_q25_commit,
)

GIT = Path(shutil.which("git") or "git")


def _qualification_inputs(path: Path) -> Path:
    path.mkdir()
    for name in sorted(M336J_QUALIFICATION_REQUIRED_FILES):
        (path / name).write_text("{}\n", encoding="utf-8", newline="\n")
    return path


def _readiness(path: Path, exact_sha: str, qualification_hash: str) -> Path:
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_PRE_FREEZE_READINESS",
        "exact_r25_sha": exact_sha,
        "qualification_input_tree_hash": qualification_hash,
        "status": "READY_FOR_HERMETIC_FINAL_ACQUISITION",
    }
    write_canonical_json(path, {**body, "readiness_hash": content_hash(body)})
    return path


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(GIT), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def test_qualification_tree_rejects_readiness_self_reference(tmp_path: Path) -> None:
    inputs = _qualification_inputs(tmp_path / "inputs")
    (inputs / "readiness_result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="self-referential"):
        qualification_input_tree_hash(inputs)


def test_q25_staging_manifest_excludes_its_own_tree_hash(tmp_path: Path) -> None:
    inputs = _qualification_inputs(tmp_path / "inputs")
    exact_sha = "a" * 40
    input_hash = qualification_input_tree_hash(inputs)
    readiness = _readiness(tmp_path / "readiness.json", exact_sha, input_hash)
    staging = tmp_path / "staging"
    receipt = build_m336j_q25_staging(
        qualification_input_root=inputs,
        readiness_result=readiness,
        output_root=staging,
        exact_r25c_sha=exact_sha,
    )
    manifest = json.loads(
        (staging / "artifacts/m336j/q25_tree_manifest.json").read_text(encoding="utf-8")
    )
    assert "q25_staging_tree_hash" not in manifest
    assert receipt.qualification_input_tree_hash == input_hash
    assert receipt.post_scan_modified_file_count == 0
    assert (
        q25_staging_receipt_from_dict(json.loads(canonical_json(asdict(receipt))))
        == receipt
    )


def test_external_post_q25_verifier_matches_pre_scanned_bytes(tmp_path: Path) -> None:
    inputs = _qualification_inputs(tmp_path / "inputs")
    input_hash = qualification_input_tree_hash(inputs)
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    _git(repository, "config", "user.name", "M336J Test")
    _git(repository, "config", "user.email", "m336j@example.invalid")
    (repository / "base.txt").write_text("R25c\n", encoding="utf-8")
    _git(repository, "add", "base.txt")
    _git(repository, "commit", "-q", "-m", "R25c-like")
    r25c = _git(repository, "rev-parse", "HEAD^{commit}")

    readiness = _readiness(tmp_path / "readiness.json", r25c, input_hash)
    staging = tmp_path / "staging"
    receipt = build_m336j_q25_staging(
        qualification_input_root=inputs,
        readiness_result=readiness,
        output_root=staging,
        exact_r25c_sha=r25c,
    )
    for source in (item for item in staging.rglob("*") if item.is_file()):
        target = repository / source.relative_to(staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    _git(repository, "add", "artifacts/m336j", "runs/m336j")
    _git(repository, "commit", "-q", "-m", M336J_Q25_SUBJECT)
    q25 = _git(repository, "rev-parse", "HEAD^{commit}")
    post = verify_m336j_post_q25_commit(
        repository=repository,
        git_executable=GIT,
        staging_root=staging,
        staging_receipt=receipt,
        exact_r25c_sha=r25c,
        exact_q25_sha=q25,
    )
    assert post.prospective_tree_hash == post.committed_tree_hash
    assert post.forbidden_changed_path_count == 0
    assert post.status == "PASS"


def test_post_q25_verifier_rejects_post_scan_mutation(tmp_path: Path) -> None:
    inputs = _qualification_inputs(tmp_path / "inputs")
    input_hash = qualification_input_tree_hash(inputs)
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    _git(repository, "config", "user.name", "M336J Test")
    _git(repository, "config", "user.email", "m336j@example.invalid")
    (repository / "base.txt").write_text("R25c\n", encoding="utf-8")
    _git(repository, "add", "base.txt")
    _git(repository, "commit", "-q", "-m", "R25c-like")
    r25c = _git(repository, "rev-parse", "HEAD^{commit}")
    readiness = _readiness(tmp_path / "readiness.json", r25c, input_hash)
    staging = tmp_path / "staging"
    receipt = build_m336j_q25_staging(
        qualification_input_root=inputs,
        readiness_result=readiness,
        output_root=staging,
        exact_r25c_sha=r25c,
    )
    for source in (item for item in staging.rglob("*") if item.is_file()):
        target = repository / source.relative_to(staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    _git(repository, "add", "artifacts/m336j", "runs/m336j")
    _git(repository, "commit", "-q", "-m", M336J_Q25_SUBJECT)
    q25 = _git(repository, "rev-parse", "HEAD^{commit}")
    (staging / "runs/m336j/readiness_result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="post-Q25"):
        verify_m336j_post_q25_commit(
            repository=repository,
            git_executable=GIT,
            staging_root=staging,
            staging_receipt=receipt,
            exact_r25c_sha=r25c,
            exact_q25_sha=q25,
        )


@pytest.mark.parametrize(
    "relative_path",
    (
        "src/ai_brain/stage3/acquisition/m336j_readiness.py",
        "src/ai_brain/stage3/acquisition/m336j_lineage.py",
        "scripts/m336j_build_f25.py",
    ),
)
def test_active_m336j_authority_has_no_hard_coded_head_depth(
    relative_path: str,
) -> None:
    source = Path(relative_path).read_text(encoding="utf-8")
    assert re.search(r"HEAD(?:\^|~)[0-9]", source) is None
