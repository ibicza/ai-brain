"""Scoped non-forced backup through the existing bare Git repository."""

import argparse
import json
import os
import subprocess
import tarfile
from pathlib import Path

from m33_composition_package import sha

FILES = (
    "src/ai_brain/training/primary_composition.py",
    "scripts/m33_primary_composition_pilot.py",
    "scripts/m33_composition_package.py",
    "scripts/m33_composition_verify.py",
    "scripts/m33_composition_backup.py",
    "scripts/lexicon_composition_prepare.py",
    "scripts/lexicon_composition_update.mjs",
    "scripts/lexicon_composition_preservation.py",
    "scripts/lexicon_catalogue_export.py",
    "tests/test_primary_composition.py",
    "tests/test_lexicon_composition_export.py",
    "docs/m33_primary_composition.md",
    "learning_materials/visual_lexicon/README.md",
    "learning_materials/visual_lexicon/visual_lexicon.xlsx",
    "learning_materials/visual_lexicon/concepts.csv",
    "learning_materials/visual_lexicon/media.csv",
    "learning_materials/visual_lexicon/text_candidates.csv",
    "learning_materials/visual_lexicon/coverage.csv",
    "learning_materials/visual_lexicon/review_queue.csv",
    "learning_materials/visual_lexicon/catalogue.json.gz",
    "learning_materials/visual_lexicon/catalogue_report.json",
    "learning_materials/visual_lexicon/composition_vocabulary.json",
    "learning_materials/visual_lexicon/composition_vocabulary_mapping.json",
    "learning_materials/visual_lexicon/composition_result_v1.json",
    "learning_materials/visual_lexicon/composition_result_v2.json",
    "learning_materials/visual_lexicon/composition_arithmetic_replay_v2.json",
)
PARENT = "31f3bb9e9afbcb71259dbdb065f0df6f9af3304d"
HEAD = "38082dd1eab82ebfff46ad3c55f5021068909f83"
INDEX = "76481e2e09d105ab876bf54c6a27e6c8c03935a9e6eab091e34e235f7498f9ef"
WORKBOOK = "5fc720687dd2d277f9ee7f432e4f56550311a0eb811b0e53b853e9dd95c89b4e"
REF = "refs/heads/codex/belarus-primary-materials-catalog"


def backup(repo, root):
    v1, v2 = [root / "visual-lexicon" / f"composition-20261009-v{i}" for i in (1, 2)]
    output = v2 / "backup-evidence.tgz"
    index = v2 / "backup-isolated.index"
    if output.exists() or index.exists():
        raise ValueError("Fresh backup paths required")
    sources = []
    for version in (v1, v2):
        sources.extend(
            (p, version.name + "/" + p.relative_to(version).as_posix())
            for p in (version / "experiment").rglob("*")
            if p.is_file()
        )
        sources.append(
            (version / "source-capsule.tgz", version.name + "/source-capsule.tgz")
        )
    sources.extend(
        (p, v2.name + "/" + p.relative_to(v2).as_posix())
        for p in (v2 / "catalogue-media").rglob("*.png")
    )
    for relative in (
        "previous.pt",
        "verifier-executed.py",
        "independent-arithmetic-replay.json",
        "remote-tests.xml",
        "focused-tests.xml",
        "catalogue-final/preservation.json",
        "catalogue-final/final-prepared.json",
        "catalogue-final/before-40bef10f.xlsx",
    ):
        sources.append((v2 / relative, v2.name + "/" + relative))
    manifest = []
    with tarfile.open(output, "x:gz") as archive:
        for path, name in sorted(sources, key=lambda x: x[1]):
            before = sha(path)
            archive.add(path, arcname=name, recursive=False)
            if sha(path) != before:
                raise ValueError("Backup input changed")
            manifest.append(
                {"file": name, "sha256": before, "bytes": path.stat().st_size}
            )
    with tarfile.open(output) as archive:
        import hashlib

        for row in manifest:
            with archive.extractfile(row["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("Archive roundtrip mismatch")
    manifest_file = v2 / "backup-manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "parent": PARENT,
                "files": manifest,
                "bundle_sha256": sha(output),
                "production_admitted": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    bare = root / "visual-lexicon/archives/catalogue-backup.git"
    env = dict(os.environ, GIT_INDEX_FILE=str(index))

    def git(*args, main=False, input=None):
        command = (
            ["git", "-C", str(repo)] if main else ["git", "--git-dir=" + str(bare)]
        )
        return subprocess.run(
            command + list(args),
            env=os.environ if main else env,
            input=input,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        ).stdout.strip()

    def protect():
        if (
            git("rev-parse", "HEAD", main=True) != HEAD
            or sha(repo / ".git/index") != INDEX
            or sha(repo / "learning_materials/visual_lexicon/visual_lexicon.xlsx")
            != WORKBOOK
        ):
            raise ValueError("User checkout or canonical catalogue changed")

    protect()
    if (
        git("rev-parse", REF) != PARENT
        or git("ls-remote", "--heads", "origin", REF).split()[0] != PARENT
    ):
        raise ValueError("Backup branch changed; no overwrite")
    files = {name: repo / name for name in FILES}
    prefix = "learning_materials/visual_lexicon/backups/composition-20261009/"
    files[prefix + "evidence.tgz"] = output
    files[prefix + "manifest.json"] = manifest_file
    git("read-tree", PARENT)
    hashes = {}
    for name, path in files.items():
        hashes[name] = sha(path)
        blob = git("hash-object", "--no-filters", "-w", str(path.resolve()))
        if sha(path) != hashes[name]:
            raise ValueError("Input changed while staging backup")
        git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + name)
    commit = git(
        "commit-tree",
        git("write-tree"),
        "-p",
        PARENT,
        input="Own compositional attribute pilot, two versions, strict rejected transfer, permanent vocabulary and exact media backup\n",
    )
    changed = git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", PARENT, commit
    ).splitlines()
    if (
        not changed
        or not set(changed).issubset(files)
        or any(sha(files[n]) != h for n, h in hashes.items())
    ):
        raise ValueError("Backup scope changed")
    protect()
    git("update-ref", REF, commit, PARENT)
    git("push", "origin", REF + ":" + REF)
    if git("ls-remote", "--heads", "origin", REF).split()[0] != commit:
        raise ValueError("Remote backup not confirmed")
    protect()
    receipt = {
        "status": "SCOPED_BACKUP_PUSH_CONFIRMED",
        "commit": commit,
        "parent": PARENT,
        "changed_paths": changed,
        "source_sha256": hashes,
        "main_head_unchanged": HEAD,
        "main_index_unchanged_sha256": INDEX,
        "canonical_workbook_sha256": WORKBOOK,
        "bundle_sha256": sha(output),
        "production_admitted": False,
    }
    (v2 / "backup-push-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "commit": commit,
                "changed_paths": len(changed),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    backup(args.repo.resolve(), args.data_root.resolve())
