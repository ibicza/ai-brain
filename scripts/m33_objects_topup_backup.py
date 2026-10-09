"""Scope-only bare Git backup; never stage or commit the dirty main checkout."""

import argparse
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_topup_evidence import PARENT, load

HEAD = "38082dd1eab82ebfff46ad3c55f5021068909f83"
INDEX_SHA = "76481e2e09d105ab876bf54c6a27e6c8c03935a9e6eab091e34e235f7498f9ef"
REF = "refs/heads/codex/belarus-primary-materials-catalog"
MODULES = (
    "src/ai_brain/training/primary_objects.py",
    "scripts/m33_primary_objects_pilot.py",
    "scripts/m33_objects_select.py",
    "scripts/m33_objects_photo_round.py",
    "scripts/m33_objects_photo_merge.py",
    "scripts/m33_objects_photo_coverage.py",
    "scripts/m33_objects_capacity_probe_remote.py",
    "scripts/m33_objects_context_probe_report.py",
    "scripts/m33_objects_topup_remote.py",
    "scripts/m33_objects_capsule.py",
    "scripts/m33_objects_publish_prepare.py",
    "scripts/m33_objects_topup_evidence.py",
    "scripts/m33_objects_topup_backup.py",
    "tests/test_primary_objects_vision_extension.py",
    "tests/test_primary_objects_selection.py",
    "tests/test_primary_objects_photo_round.py",
    "tests/test_primary_objects_photo_merge.py",
    "tests/test_primary_objects_photo_coverage.py",
    "tests/test_primary_objects.py",
    "tests/test_primary_objects_topup_evidence.py",
)
CATALOGUE = (
    "visual_lexicon.xlsx",
    "concepts.csv",
    "media.csv",
    "text_candidates.csv",
    "coverage.csv",
    "review_queue.csv",
    "catalogue.json.gz",
    "catalogue_report.json",
    "objects_photo_topup_review.json",
    "objects_photo_targeted_review.json",
    "objects_photo_topup_queries.json",
    "objects_photo_topup_cohort_caps.json",
    "objects_photo_targeted_queries.json",
    "objects_photo_targeted_cohort_caps.json",
    "objects_photo_topup_result.json",
)


def backup(repo, root, archive):
    bare = root.parent / "archives/catalogue-backup.git"
    index = root / "backup-isolated.index"
    if index.exists() or (root / "backup-push-receipt.json").exists():
        raise ValueError("Fresh isolated backup index/receipt required")
    env = dict(os.environ, GIT_INDEX_FILE=str(index.resolve()))

    def git(*args, input=None, isolate=True):
        command = (
            ["git", "--git-dir=" + str(bare)] if isolate else ["git", "-C", str(repo)]
        )
        return subprocess.run(
            command + list(args),
            input=input,
            text=True,
            encoding="utf-8",
            env=env if isolate else os.environ,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def protect():
        if (
            git("rev-parse", "HEAD", isolate=False) != HEAD
            or sha(repo / ".git/index") != INDEX_SHA
        ):
            raise ValueError("Main HEAD/index changed; preserve and review")

    protect()
    if (
        git("rev-parse", REF) != PARENT
        or git("ls-remote", "--heads", "origin", REF).split()[0] != PARENT
    ):
        raise ValueError("Backup branch advanced; no overwrite allowed")
    manifest = load(archive / "backup-manifest.json")
    if manifest["parent_backup_commit"] != PARENT:
        raise ValueError("Archive parent differs")
    sources = {name: repo / name for name in MODULES}
    sources.update(
        {
            "learning_materials/visual_lexicon/" + n: repo
            / "learning_materials/visual_lexicon"
            / n
            for n in CATALOGUE
        }
    )
    prefix = "learning_materials/visual_lexicon/backups/objects-photo-topup-20261009/"
    sources[prefix + "backup-manifest.json"] = archive / "backup-manifest.json"
    for part in manifest["bundles"]:
        path = archive / part["file"]
        if sha(path) != part["sha256"]:
            raise ValueError("Archive bytes changed")
        sources[prefix + part["file"]] = path
    publication = load(root / "publication/saved-xlsx-preservation-extended.json")
    if (
        sha(sources["learning_materials/visual_lexicon/visual_lexicon.xlsx"])
        != publication["candidate_sha256"]
    ):
        raise ValueError("Canonical workbook is not verified candidate")
    git("read-tree", PARENT)
    hashes = {}
    for name, source in sorted(sources.items()):
        digest = sha(source)
        blob = git("hash-object", "--no-filters", "-w", str(source.resolve()))
        if sha(source) != digest:
            raise ValueError("Backup source changed")
        git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + name)
        hashes[name] = digest
    tree = git("write-tree")
    commit = git(
        "commit-tree",
        tree,
        "-p",
        PARENT,
        input="Own vision: 730 fresh curated photos, matched 64/128 training and frozen evaluation; no production activation\n",
    )
    changed = git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", PARENT, commit
    ).splitlines()
    if not changed or not set(changed).issubset(sources):
        raise ValueError("Out-of-scope backup diff")
    for name, digest in hashes.items():
        if sha(sources[name]) != digest:
            raise ValueError("Source changed before publication")
    protect()
    git("update-ref", REF, commit, PARENT)
    git("push", "origin", REF + ":" + REF)
    if git("ls-remote", "--heads", "origin", REF).split()[0] != commit:
        raise ValueError("Remote backup SHA not confirmed")
    protect()
    receipt = {
        "status": "SCOPED_BACKUP_PUSH_CONFIRMED",
        "commit": commit,
        "parent": PARENT,
        "branch": REF,
        "changed_paths": changed,
        "source_sha256": hashes,
        "main_head_unchanged": HEAD,
        "main_index_unchanged_sha256": INDEX_SHA,
    }
    write_json(root / "backup-push-receipt.json", receipt)
    return {k: receipt[k] for k in ("status", "commit", "branch")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "root", "archive"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(backup(args.repo, args.root, args.archive))
