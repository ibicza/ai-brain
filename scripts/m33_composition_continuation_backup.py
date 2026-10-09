"""Append continuation evidence to the existing non-forced backup branch."""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

from m33_composition_backup import HEAD, INDEX, REF, WORKBOOK
from m33_composition_package import sha

FILES = (
    "src/ai_brain/training/primary_composition.py",
    "scripts/m33_primary_composition_pilot.py",
    "scripts/m33_composition_package.py",
    "scripts/m33_composition_verify.py",
    "scripts/m33_composition_remote.py",
    "scripts/m33_composition_diagnostics.py",
    "scripts/m33_composition_compare.py",
    "scripts/m33_composition_continuation_backup.py",
    "tests/test_primary_composition.py",
    "tests/test_primary_composition_pipeline.py",
    "tests/test_primary_composition_comparison.py",
    "docs/m33_primary_composition_continuation.md",
    "learning_materials/visual_lexicon/README.md",
    "learning_materials/visual_lexicon/composition_result_v3.json",
    "learning_materials/visual_lexicon/composition_result_v4.json",
    "learning_materials/visual_lexicon/composition_result_v5.json",
    "learning_materials/visual_lexicon/composition_arithmetic_replay_v3.json",
    "learning_materials/visual_lexicon/composition_arithmetic_replay_v4.json",
    "learning_materials/visual_lexicon/composition_arithmetic_replay_v5.json",
    "learning_materials/visual_lexicon/composition_comparison_v4.json",
    "learning_materials/visual_lexicon/composition_comparison_v5.json",
)


def run(repo, data, parent):
    if len(parent) != 40 or any(c not in "0123456789abcdef" for c in parent):
        raise ValueError("Explicit expected parent required")
    runs = [data / "visual-lexicon" / f"composition-20261010-v{n}" for n in (3, 4, 5)]
    bundle, manifest_file, index = [
        runs[-1] / name
        for name in (
            "backup-evidence.tgz",
            "backup-manifest.json",
            "backup-isolated.index",
        )
    ]
    if any(p.exists() for p in (bundle, manifest_file, index)):
        raise ValueError("Fresh backup paths required")
    bare = data / "visual-lexicon/archives/catalogue-backup.git"
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
            raise ValueError("User checkout or canonical workbook changed")

    protect()
    if (
        git("rev-parse", REF) != parent
        or git("ls-remote", "--heads", "origin", REF).split()[0] != parent
    ):
        raise ValueError("Backup branch changed; no overwrite")
    sources = []
    for root in runs:
        if root.resolve().parent != (data / "visual-lexicon").resolve():
            raise ValueError("Run escaped its explicit directory")
        sources += [
            (
                p,
                root.name
                + "/experiment/"
                + p.relative_to(root / "experiment").as_posix(),
            )
            for p in (root / "experiment").rglob("*")
            if p.is_file()
        ]
        # Exact allowlist; no test-temp trees, junctions or unrelated data.
        for name in (
            "source-capsule.tgz",
            "previous.pt",
            "warm-candidate.pt",
            "remote-receipt.json",
            "remote-tests.xml",
            "independent-arithmetic-replay.json",
            "development-diagnostics.json",
            "transport-executed.py",
        ):
            sources.append((root / name, root.name + "/" + name))
        for name in (
            "supplemental-verifier-executed.py",
            "supplemental-verifier-v2-executed.py",
            "supplemental-verifier-v3-executed.py",
            "supplemental-replay.json",
            "supplemental-replay-v3.json",
            "regression-tests-pathfix.xml",
            "pipeline-tests.xml",
            "spatial-tests.xml",
            "final-regression-tests.xml",
            "final-regression-confirmed.xml",
            "geometry-regression-tests.xml",
            "backward-replay-tests.xml",
            "lineage-tests.xml",
            "same-pixel-comparison.json",
            "comparison-executed.py",
            "comparison-arithmetic-executed.py",
            "recovery-verifier-executed.py",
        ):
            if (root / name).exists():
                sources.append((root / name, root.name + "/" + name))
    rows = []
    with tarfile.open(bundle, "x:gz") as archive:
        for path, name in sorted(sources, key=lambda pair: pair[1]):
            digest = sha(path)
            archive.add(path, arcname=name, recursive=False)
            if sha(path) != digest:
                raise ValueError("Evidence changed during archive")
            rows.append({"file": name, "sha256": digest, "bytes": path.stat().st_size})
    with tarfile.open(bundle) as archive:
        for row in rows:
            with archive.extractfile(row["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("Archive byte replay differs")
    # Bound each Git blob instead of trying to push one large experiment tar.
    # Concatenation reconstructs the exact archive; no data are discarded.
    parts = []
    with bundle.open("rb") as stream:
        while block := stream.read(32 * 1024 * 1024):
            path = runs[-1] / f"backup-evidence.part{len(parts):03d}.bin"
            with path.open("xb") as destination:
                destination.write(block)
            parts.append(path)
    replay_digest = hashlib.sha256()
    for part in parts:
        with part.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                replay_digest.update(block)
    if replay_digest.hexdigest() != sha(bundle):
        raise ValueError("Archive part concatenation differs")
    manifest_file.write_text(
        json.dumps(
            {
                "files": rows,
                "bundle_sha256": sha(bundle),
                "parts": [
                    {"file": p.name, "sha256": sha(p), "bytes": p.stat().st_size}
                    for p in parts
                ],
                "parent": parent,
                "production_admitted": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    prefix = "learning_materials/visual_lexicon/backups/composition-20261010/"
    files = {name: repo / name for name in FILES}
    files.update({prefix + p.name: p for p in parts})
    files[prefix + "manifest.json"] = manifest_file
    git("read-tree", parent)
    hashes = {}
    for name, path in files.items():
        hashes[name] = sha(path)
        blob = git("hash-object", "--no-filters", "-w", str(path.resolve()))
        if sha(path) != hashes[name]:
            raise ValueError("Source changed while staging")
        git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + name)
    commit = git(
        "commit-tree",
        git("write-tree"),
        "-p",
        parent,
        input="Own compositional continuation: diverse scenes, spatial readout, measured candidates and replay evidence\n",
    )
    changed = git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", parent, commit
    ).splitlines()
    if (
        not changed
        or not set(changed).issubset(files)
        or any(sha(files[n]) != h for n, h in hashes.items())
    ):
        raise ValueError("Backup scope changed")
    protect()
    git("update-ref", REF, commit, parent)
    git("push", "origin", REF + ":" + REF)
    if git("ls-remote", "--heads", "origin", REF).split()[0] != commit:
        raise ValueError("Remote backup not confirmed")
    protect()
    receipt = {
        "status": "SCOPED_BACKUP_PUSH_CONFIRMED",
        "commit": commit,
        "parent": parent,
        "changed_paths": changed,
        "source_sha256": hashes,
        "main_head_unchanged": HEAD,
        "main_index_unchanged_sha256": INDEX,
        "canonical_workbook_sha256": WORKBOOK,
        "bundle_sha256": sha(bundle),
        "production_admitted": False,
    }
    (runs[-1] / "backup-push-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
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
    for name in ("repo", "data-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-parent", required=True)
    args = parser.parse_args()
    run(args.repo.resolve(), args.data_root.resolve(), args.expected_parent)
