"""Isolated narrow Git backup for the development-only readout experiment."""

import argparse
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_readout_evidence import PARENT, WORKBOOK, load
from m33_objects_topup_backup import HEAD, INDEX_SHA, REF

FILES = (
    "src/ai_brain/training/primary_objects.py",
    "src/ai_brain/training/primary_object_augmentation.py",
    "scripts/m33_primary_objects_pilot.py",
    "scripts/m33_objects_select.py",
    "scripts/m33_objects_capsule.py",
    "scripts/m33_objects_context_probe_report.py",
    "scripts/m33_objects_readout_remote.py",
    "scripts/m33_objects_readout_evidence.py",
    "scripts/m33_objects_readout_backup.py",
    "scripts/requirements-primary-vision.txt",
    "scripts/m33_objects_prompt_diagnostic.py",
    "tests/test_primary_objects_readout.py",
    "tests/test_primary_objects_prompt_diagnostic.py",
    "learning_materials/visual_lexicon/objects_readout_development_result.json",
)


def backup(repo, root, archive):
    bare = root.parent / "archives/catalogue-backup.git"
    index = root / "backup-isolated.index"
    if index.exists():
        raise ValueError("Fresh isolated index required")
    env = dict(os.environ, GIT_INDEX_FILE=str(index.resolve()))

    def git(*args, input=None, main=False):
        command = (
            ["git", "-C", str(repo)] if main else ["git", "--git-dir=" + str(bare)]
        )
        return subprocess.run(
            command + list(args),
            input=input,
            text=True,
            encoding="utf-8",
            env=os.environ if main else env,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def protect():
        if (
            git("rev-parse", "HEAD", main=True) != HEAD
            or sha(repo / ".git/index") != INDEX_SHA
        ):
            raise ValueError("Main HEAD/index changed; preserve and review")
        if (
            sha(repo / "learning_materials/visual_lexicon/visual_lexicon.xlsx")
            != WORKBOOK
        ):
            raise ValueError("Canonical workbook changed; preserve and review")

    protect()
    if (
        git("rev-parse", REF) != PARENT
        or git("ls-remote", "--heads", "origin", REF).split()[0] != PARENT
    ):
        raise ValueError("Backup branch changed; no overwrite allowed")
    manifest = load(archive / "backup-manifest.json")
    if manifest["parent_backup_commit"] != PARENT:
        raise ValueError("Archive parent changed")
    sources = {name: repo / name for name in FILES}
    prefix = "learning_materials/visual_lexicon/backups/objects-readout-20261009/"
    sources[prefix + "backup-manifest.json"] = archive / "backup-manifest.json"
    for part in manifest["bundles"]:
        path = archive / part["file"]
        if sha(path) != part["sha256"]:
            raise ValueError("Archive bytes changed")
        sources[prefix + part["file"]] = path
    git("read-tree", PARENT)
    hashes = {}
    for name, path in sorted(sources.items()):
        hashes[name] = sha(path)
        blob = git("hash-object", "--no-filters", "-w", str(path.resolve()))
        if sha(path) != hashes[name]:
            raise ValueError("Backup input changed")
        git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + name)
    commit = git(
        "commit-tree",
        git("write-tree"),
        "-p",
        PARENT,
        input="Own visual readout: protected 2x2 development experiment; no new final or production admission\n",
    )
    changed = git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", PARENT, commit
    ).splitlines()
    if not changed or not set(changed).issubset(sources):
        raise ValueError("Out-of-scope backup diff")
    if any(sha(sources[n]) != d for n, d in hashes.items()):
        raise ValueError("Source changed before backup publication")
    protect()
    git("update-ref", REF, commit, PARENT)
    git("push", "origin", REF + ":" + REF)
    if git("ls-remote", "--heads", "origin", REF).split()[0] != commit:
        raise ValueError("Remote backup SHA not confirmed")
    protect()
    write_json(
        root / "backup-push-receipt.json",
        {
            "status": "SCOPED_BACKUP_PUSH_CONFIRMED",
            "commit": commit,
            "parent": PARENT,
            "branch": REF,
            "changed_paths": changed,
            "source_sha256": hashes,
            "main_head_unchanged": HEAD,
            "main_index_unchanged_sha256": INDEX_SHA,
            "canonical_workbook_unchanged_sha256": WORKBOOK,
        },
    )
    return {"commit": commit, "status": "SCOPED_BACKUP_PUSH_CONFIRMED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "root", "archive"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(backup(args.repo, args.root, args.archive))
