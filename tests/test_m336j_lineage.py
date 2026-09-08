from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_lineage import (
    M336J_GIT_LINEAGE_LAYER,
    M336JGitLineageError,
    build_implementation_lineage_policy,
    implementation_lineage_receipt_from_dict,
    verify_m336j_implementation_lineage,
    verify_supplied_implementation_lineage_receipt,
)

GIT = Path(shutil.which("git") or "git")
SUBJECTS = ("R25a-like", "R25b-like", "R25c-like")


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        (str(GIT), *arguments),
        cwd=repository,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "M336J Test")
    _git(path, "config", "user.email", "m336j@example.invalid")
    return path


def _commit(repository: Path, subject: str) -> str:
    parent = _git(repository, "rev-parse", "HEAD^{commit}", check=False)
    target = repository / f"commit-{content_hash((subject, parent))[:16]}.txt"
    target.write_text(subject + "\n", encoding="utf-8", newline="\n")
    _git(repository, "add", target.name)
    _git(repository, "commit", "-q", "-m", subject)
    return _git(repository, "rev-parse", "HEAD^{commit}")


def _chain(path: Path) -> tuple[Path, str, str, str, str]:
    repository = _repository(path)
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    r25b = _commit(repository, SUBJECTS[1])
    r25c = _commit(repository, SUBJECTS[2])
    return repository, base, r25a, r25b, r25c


def _policy(
    base: str,
    r25a: str,
    r25b: str,
    r25c: str,
    *,
    subjects: tuple[str, str, str] = SUBJECTS,
):
    return build_implementation_lineage_policy(
        exact_base_f24_sha=base,
        exact_r25a_sha=r25a,
        exact_r25b_sha=r25b,
        current_implementation_head_sha=r25c,
        expected_subjects=subjects,
    )


def _assert_lineage_failure(repository: Path, policy) -> None:
    with pytest.raises(M336JGitLineageError, match=M336J_GIT_LINEAGE_LAYER):
        verify_m336j_implementation_lineage(repository, GIT, policy)


def test_exact_linear_f24_r25a_r25b_r25c_passes(tmp_path: Path) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "exact")
    receipt = verify_m336j_implementation_lineage(
        repository, GIT, _policy(base, r25a, r25b, r25c)
    )
    assert receipt.ordered_implementation_shas == (r25a, r25b, r25c)
    assert receipt.merge_count == 0
    assert receipt.status == "PASS"


def test_historical_head_second_parent_fails_on_linear_r25b(tmp_path: Path) -> None:
    repository, _base, _r25a, r25b, _r25c = _chain(tmp_path / "historical")
    _git(repository, "checkout", "-q", "--detach", r25b)
    result = subprocess.run(
        (str(GIT), "rev-parse", "HEAD^2"),
        cwd=repository,
        check=False,
        capture_output=True,
    )
    assert result.returncode != 0


def test_naive_first_parent_depth_points_to_r25a_at_r25c(tmp_path: Path) -> None:
    repository, base, r25a, _r25b, _r25c = _chain(tmp_path / "naive")
    assert _git(repository, "rev-parse", "HEAD~2") == r25a
    assert r25a != base


def test_r25a_parent_changed_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "r25a-parent")
    base = _commit(repository, "F24-like")
    _commit(repository, "unexpected bridge")
    r25a = _commit(repository, SUBJECTS[0])
    r25b = _commit(repository, SUBJECTS[1])
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_r25b_parent_changed_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "r25b-parent")
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    _commit(repository, "unexpected bridge")
    r25b = _commit(repository, SUBJECTS[1])
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_r25c_parent_changed_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "r25c-parent")
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    r25b = _commit(repository, SUBJECTS[1])
    _commit(repository, "unexpected bridge")
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_r25a_omitted_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "omit-r25a")
    base = _commit(repository, "F24-like")
    _git(repository, "checkout", "-q", "-b", "omitted", base)
    omitted_r25a = _commit(repository, SUBJECTS[0])
    _git(repository, "checkout", "-q", "main")
    r25b = _commit(repository, SUBJECTS[1])
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, omitted_r25a, r25b, r25c))


def test_r25b_omitted_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "omit-r25b")
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    _git(repository, "checkout", "-q", "-b", "omitted", r25a)
    omitted_r25b = _commit(repository, SUBJECTS[1])
    _git(repository, "checkout", "-q", "main")
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, r25a, omitted_r25b, r25c))


def test_extra_implementation_commit_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "extra")
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    r25b = _commit(repository, SUBJECTS[1])
    _commit(repository, "extra implementation")
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_implementation_order_changed_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository, base, first, second, r25c = _chain(tmp_path / "order")
    _assert_lineage_failure(
        repository,
        _policy(
            base,
            second,
            first,
            r25c,
            subjects=(SUBJECTS[1], SUBJECTS[0], SUBJECTS[2]),
        ),
    )


def test_r25c_merge_commit_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "merge-current")
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    _git(repository, "checkout", "-q", "-b", "side", r25a)
    _commit(repository, "side work")
    _git(repository, "checkout", "-q", "main")
    r25b = _commit(repository, SUBJECTS[1])
    _git(repository, "merge", "-q", "--no-ff", "side", "-m", SUBJECTS[2])
    r25c = _git(repository, "rev-parse", "HEAD^{commit}")
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_side_branch_merge_inserted_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "merge-inserted")
    base = _commit(repository, "F24-like")
    r25a = _commit(repository, SUBJECTS[0])
    _git(repository, "checkout", "-q", "-b", "side", r25a)
    _commit(repository, "side work")
    _git(repository, "checkout", "-q", "main")
    r25b = _commit(repository, SUBJECTS[1])
    _git(repository, "merge", "-q", "--no-ff", "side", "-m", "merge side")
    r25c = _commit(repository, SUBJECTS[2])
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_unrelated_base_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "unrelated-base")
    _git(repository, "checkout", "-q", "--orphan", "unrelated")
    _git(repository, "rm", "-q", "-rf", ".")
    unrelated = _commit(repository, "unrelated root")
    _git(repository, "checkout", "-q", "main")
    assert unrelated != base
    _assert_lineage_failure(repository, _policy(unrelated, r25a, r25b, r25c))


def test_f24_not_ancestor_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "not-ancestor")
    other = _repository(tmp_path / "other")
    foreign_base = _commit(other, "foreign F24")
    assert foreign_base != base
    _assert_lineage_failure(repository, _policy(foreign_base, r25a, r25b, r25c))


def test_detached_unrelated_head_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "detached")
    _git(repository, "checkout", "-q", "--detach", base)
    unrelated = _commit(repository, "detached unrelated")
    assert unrelated != r25c
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_request_sha_differs_from_live_head_fails_at_lineage_layer(
    tmp_path: Path,
) -> None:
    repository, base, r25a, r25b, _r25c = _chain(tmp_path / "request-sha")
    fake = "f" * 40
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, fake))


def test_dirty_worktree_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "dirty")
    (repository / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    _assert_lineage_failure(repository, _policy(base, r25a, r25b, r25c))


def test_frozen_commit_subject_changed_fails_at_lineage_layer(tmp_path: Path) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "subject")
    _assert_lineage_failure(
        repository,
        _policy(
            base,
            r25a,
            r25b,
            r25c,
            subjects=(SUBJECTS[0], "changed subject", SUBJECTS[2]),
        ),
    )


def test_shallow_incomplete_history_fails_at_lineage_layer(tmp_path: Path) -> None:
    source, base, r25a, r25b, r25c = _chain(tmp_path / "source")
    shallow = tmp_path / "shallow"
    subprocess.run(
        (str(GIT), "clone", "-q", "--depth", "2", source.as_uri(), str(shallow)),
        check=True,
        capture_output=True,
    )
    _assert_lineage_failure(shallow, _policy(base, r25a, r25b, r25c))


def test_rehashed_fake_supplied_receipt_fails_at_lineage_layer(
    tmp_path: Path,
) -> None:
    repository, base, r25a, r25b, r25c = _chain(tmp_path / "fake-receipt")
    policy = _policy(base, r25a, r25b, r25c)
    receipt = verify_m336j_implementation_lineage(repository, GIT, policy)
    fake = replace(receipt, policy_hash="f" * 64, receipt_hash="")
    body = asdict(fake)
    body.pop("receipt_hash")
    fake = replace(fake, receipt_hash=content_hash(body))
    reparsed = implementation_lineage_receipt_from_dict(
        json.loads(canonical_json(fake))
    )
    with pytest.raises(M336JGitLineageError, match=M336J_GIT_LINEAGE_LAYER):
        verify_supplied_implementation_lineage_receipt(
            repository, GIT, policy, reparsed
        )
