"""Hash-checked scoped backup, without touching the user's checkout or index.

Large original files are stored in <=32 MiB chunks, not a second aggregate tar.
Restore chunks in manifest order and verify original byte SHA256 before use.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from m33_composition_backup import HEAD, INDEX, REF, WORKBOOK
from m33_composition_package import sha

SOURCE_FILES = (
    "src/ai_brain/training/primary_composition.py",
    "src/ai_brain/training/primary_composition_views.py",
    "src/ai_brain/training/primary_composition_controls.py",
    "src/ai_brain/training/primary_composition_rng_audit.py",
    "src/ai_brain/training/primary_numeric_backend.py",
    "src/ai_brain/training/primary_zero.py",
    "src/ai_brain/training/primary_relations.py",
    "scripts/m33_primary_composition_pilot.py",
    "scripts/m33_composition_package.py",
    "scripts/m33_composition_verify.py",
    "scripts/m33_composition_remote.py",
    "scripts/m33_composition_control_screen.py",
    "scripts/m33_composition_control_remote.py",
    "scripts/m33_composition_background_probe.py",
    "scripts/m33_composition_rng_audit.py",
    "scripts/m33_composition_dev_probe.py",
    "scripts/m33_composition_dev_remote.py",
    "scripts/m33_composition_numeric_probe.py",
    "scripts/m33_composition_novel_controls.py",
    "scripts/m33_composition_novel_screen.py",
    "scripts/m33_composition_novel_remote.py",
    "scripts/requirements-primary-materials.txt",
    "scripts/m33_composition_sixhour_backup.py",
    "tests/test_primary_composition.py",
    "tests/test_primary_composition_pipeline.py",
    "tests/test_primary_composition_views.py",
    "tests/test_primary_composition_controls.py",
    "tests/test_primary_composition_backup.py",
    "tests/test_primary_composition_package.py",
    "tests/test_primary_composition_dev_probe.py",
    "tests/test_primary_composition_numeric_probe.py",
    "tests/test_primary_numeric_backend.py",
    "tests/test_primary_composition_backgrounds.py",
    "tests/test_primary_composition_novel_controls.py",
    "tests/test_primary_composition_novel_screen.py",
    "tests/test_primary_composition_novel_remote.py",
    "tests/test_primary_zero.py",
    "tests/test_primary_relations.py",
    "docs/m33_composition_six_hour_work.md",
    "docs/m33_primary_composition_continuation.md",
    "learning_materials/visual_lexicon/README.md",
)
RUN_ROOT_FILES = (
    "source-capsule.tgz",
    "previous.pt",
    "warm-candidate.pt",
    "remote-receipt.json",
    "remote-tests.xml",
    "independent-arithmetic-replay.json",
    "transport-executed.py",
    "same-pixel-comparison.json",
    "comparison-executed.py",
    "development-diagnostics.json",
    "known-transfer-error-2447.png",
    "known-transfer-error-2075.png",
    "scientific-validity-notice.json",
    "remote-preflight-failure.json",
)


def chunks(path, destination, *, limit=32 * 1024 * 1024):
    """Stream large bytes once; validate reconstruction without aggregate copy."""
    if (
        destination.exists()
        or type(limit) is not int
        or not 1 <= limit <= 32 * 1024 * 1024
    ):
        raise ValueError("Fresh positive-sized chunk output required")
    before = sha(path)
    destination.mkdir(parents=True)
    parts = []
    combined = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(limit):
            part = destination / f"part{len(parts):03d}.bin"
            with part.open("xb") as stream:
                stream.write(block)
            # Independent read, not merely hashing the source input block.
            check = part.read_bytes()
            combined.update(check)
            parts.append({"file": part.name, "sha256": sha(part), "bytes": len(check)})
    if sha(path) != before or combined.hexdigest() != before:
        raise ValueError("Original or reconstructed chunk bytes differ")
    return {"sha256": before, "bytes": path.stat().st_size, "parts": parts}


def run(repo, data, output, parent, run_names):
    if not re.fullmatch(r"[0-9a-f]{40}", parent) or output.exists():
        raise ValueError("Expected parent and fresh output required")
    base = (data / "visual-lexicon").resolve()
    if not output.resolve().is_relative_to(base):
        raise ValueError("Backup output must stay in the project data directory")
    if len(set(run_names)) != len(run_names) or any(
        not re.fullmatch(r"composition-\d{8}-v\d+", n) for n in run_names
    ):
        raise ValueError("Unique scoped run names required")
    output.mkdir(parents=True)
    bare = base / "archives/catalogue-backup.git"
    env = dict(os.environ, GIT_INDEX_FILE=str(output / "isolated.index"))

    def git(*args, main=False, input=None):
        prefix = ["git", "-C", str(repo)] if main else ["git", "--git-dir=" + str(bare)]
        return subprocess.run(
            prefix + list(args),
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
            raise ValueError("User checkout/index/workbook changed; no overwrite")

    protect()
    if (
        git("rev-parse", REF) != parent
        or git("ls-remote", "--heads", "origin", REF).split()[0] != parent
    ):
        raise ValueError("Backup branch changed; never force")
    files = {name: repo / name for name in SOURCE_FILES}
    evidence = []
    for name in run_names:
        root = base / name
        if root.resolve().parent != base:
            raise ValueError("Scoped run required")
        completed = root / "remote-receipt.json"
        failed = root / "remote-preflight-failure.json"
        receipt = completed if completed.is_file() else failed
        if not receipt.is_file() or json.loads(receipt.read_text())["status"] not in (
            "REMOTE_CONTINUATION_REPLAYED",
            "REMOTE_PREFLIGHT_FAILED_NOT_TRAINED",
        ):
            raise ValueError("Completed replay or preserved preflight failure required")
        selected = [root / n for n in RUN_ROOT_FILES if (root / n).is_file()]
        for child in (
            "experiment",
            "control-screen-v1",
            "background-probe-v1",
            "development-agreement-v1",
            "development-agreement-v2",
            "numeric-backend-v1",
            "cold-family-screen-v1",
            "cold-family-screen-v2",
        ):
            if (root / child).exists():
                selected += [
                    p
                    for p in (root / child).rglob("*")
                    if p.is_file()
                    and "frozen-source" not in p.relative_to(root / child).parts
                ]
        for path in sorted(selected):
            if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
                raise ValueError("Non-local evidence rejected")
            relative = path.relative_to(root).as_posix()
            evidence.append((name + "/" + relative, path))
    for name in (
        "rng-shortcut-audit-20261010.json",
        "rng-shortcut-audit-20261010-v2.json",
        "qa-sixhour-rng-full-tests.xml",
        "qa-sixhour-rng-fixed-tests.xml",
        "qa-sixhour-backup-v1-tests.xml",
        "qa-sixhour-backup-v2-tests.xml",
        "qa-sixhour-diverse-controls-v1.xml",
        "qa-sixhour-numeric-contract-v1.xml",
        "qa-sixhour-background-source-v1.xml",
        "qa-sixhour-wide-backgrounds-v1.xml",
        "qa-sixhour-wide-full-regression-v1.xml",
        "qa-sixhour-wide-full-regression-v2.xml",
        "qa-sixhour-pdf-extraction-v1.xml",
        "qa-sixhour-curve-focused-v1.xml",
        "qa-sixhour-curve-unit-v1.xml",
        "qa-sixhour-curve-policy-fix-v1.xml",
        "qa-sixhour-curve-full-regression-v1.xml",
        "qa-sixhour-cold-contours-v1.xml",
        "qa-sixhour-cold-pipeline-v1.xml",
        "qa-sixhour-cold-pipeline-v2.xml",
        "qa-sixhour-cold-transport-v1.xml",
    ):
        if (base / name).is_file():
            evidence.append((name, base / name))
    prefix = "learning_materials/visual_lexicon/backups/" + output.name + "/"
    manifest = []
    for name, path in evidence:
        record = {"file": name, "sha256": sha(path), "bytes": path.stat().st_size}
        if record["bytes"] > 32 * 1024 * 1024:
            destination = output / "chunks" / name
            record.update(chunks(path, destination))
            for part in record["parts"]:
                files[prefix + "chunks/" + name + "/" + part["file"]] = (
                    destination / part["file"]
                )
        else:
            files[prefix + "files/" + name] = path
        manifest.append(record)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "files": manifest,
                "parent": parent,
                "production_admitted": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    files[prefix + "manifest.json"] = manifest_path
    git("read-tree", parent)
    hashes = {}
    for name, path in files.items():
        hashes[name] = sha(path)
        blob = git("hash-object", "--no-filters", "-w", str(path.resolve()))
        if sha(path) != hashes[name]:
            raise ValueError("Source changed while backing up")
        git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + name)
    commit = git(
        "commit-tree",
        git("write-tree"),
        "-p",
        parent,
        input="Own visual composition: preserved evidence and background RNG audit\n",
    )
    changed = git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", parent, commit
    ).splitlines()
    if (
        not changed
        or not set(changed).issubset(files)
        or any(sha(files[n]) != h for n, h in hashes.items())
    ):
        raise ValueError("Backup scope/source changed")
    protect()
    git("update-ref", REF, commit, parent)
    git("push", "origin", REF + ":" + REF)
    if git("ls-remote", "--heads", "origin", REF).split()[0] != commit:
        raise ValueError("Remote push not confirmed")
    protect()
    report = {
        "status": "SCOPED_BACKUP_PUSH_CONFIRMED",
        "commit": commit,
        "parent": parent,
        "changed_paths": changed,
        "source_sha256": hashes,
        "main_head_unchanged": HEAD,
        "main_index_sha256": INDEX,
        "canonical_workbook_sha256": WORKBOOK,
        "production_admitted": False,
    }
    (output / "push-receipt.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": report["status"], "commit": commit, "files": len(changed)}
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "data-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-parent", required=True)
    parser.add_argument("--run", action="append", default=[])
    args = parser.parse_args()
    run(
        args.repo.resolve(),
        args.data_root.resolve(),
        args.output.resolve(),
        args.expected_parent,
        args.run,
    )
