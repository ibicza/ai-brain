from __future__ import annotations

from pathlib import Path, PurePosixPath

from scripts import m336k5_prepare_karina_capsule as preparation


def test_karina_bundle_preserves_complete_local_ref_closure(
    monkeypatch, tmp_path: Path
) -> None:
    git = tmp_path / "git"
    source = tmp_path / "source"
    bundle = tmp_path / "repository.bundle"
    observed: list[tuple[tuple[object, ...], Path | None]] = []

    def record(arguments: tuple[object, ...], cwd: Path | None) -> str:
        observed.append((arguments, cwd))
        return ""

    monkeypatch.setattr(preparation, "_run", record)
    preparation._create_repository_bundle(git=git, bundle=bundle, repository=source)

    assert observed == [
        ((git, "bundle", "create", str(bundle), "HEAD", "--all"), source)
    ]


def test_karina_clone_restores_remote_tracking_refs_as_local_branches() -> None:
    fetch, promote = preparation._repository_ref_restore_commands(
        remote_repository=PurePosixPath("/home/worker/m336k5-run/repository"),
        remote_bundle=PurePosixPath("/home/worker/m336k5-run/repository.bundle"),
    )

    assert "+refs/heads/*:refs/heads/*" in fetch
    assert "+refs/remotes/origin/*:refs/remotes/origin/*" in fetch
    assert "+refs/tags/*:refs/tags/*" in fetch
    assert "refs/remotes/origin" in promote
    assert "*/HEAD) continue" in promote
    assert 'update-ref "refs/heads/$name" "$sha"' in promote
