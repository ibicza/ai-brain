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
    "scripts/m33_composition_diagnostics.py",
    "scripts/m33_composition_dev_remote.py",
    "scripts/m33_composition_numeric_probe.py",
    "scripts/m33_composition_novel_controls.py",
    "scripts/m33_composition_novel_screen.py",
    "scripts/m33_composition_novel_remote.py",
    "scripts/m33_composition_source_prepare.py",
    "scripts/m33_composition_source_dataset.py",
    "examples/m33/visual_source_controls_v1.json",
    "examples/m33/visual_source_controls_v2.json",
    "examples/m33/visual_source_controls_v3.json",
    "scripts/requirements-primary-materials.txt",
    "scripts/m33_composition_sixhour_backup.py",
    "tests/test_primary_composition.py",
    "tests/test_primary_composition_pipeline.py",
    "tests/test_primary_composition_calibration.py",
    "tests/test_primary_composition_views.py",
    "tests/test_primary_composition_controls.py",
    "tests/test_primary_composition_backup.py",
    "tests/test_primary_composition_package.py",
    "tests/test_primary_composition_dev_probe.py",
    "tests/test_primary_composition_diagnostics.py",
    "tests/test_primary_composition_numeric_probe.py",
    "tests/test_primary_numeric_backend.py",
    "tests/test_primary_composition_backgrounds.py",
    "tests/test_primary_composition_novel_controls.py",
    "tests/test_primary_composition_novel_screen.py",
    "tests/test_primary_composition_novel_remote.py",
    "tests/test_primary_composition_source_prepare.py",
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
    "exposed-transfer-errors.json",
    "exposed-transfer-errors.png",
    "exposed-control-errors.json",
    "exposed-control-errors.png",
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


def git_chunks(path, put, get, *, limit=32 * 1024 * 1024):
    """Store bounded blobs directly; independently reread and reconstruct them.

    No second large chunk directory. The Git tree still contains ordinary
    partNNN.bin files, so old manifest restoration remains applicable.
    """
    if type(limit) is not int or not 1 <= limit <= 32 * 1024 * 1024:
        raise ValueError("Positive bounded chunk size required")
    before = sha(path)
    parts, combined = [], hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(limit):
            blob = put(block)
            if not isinstance(blob, str) or not re.fullmatch(r"[0-9a-f]{40}", blob):
                raise ValueError("Verified Git blob identifier required")
            restored = get(blob)
            if restored != block:
                raise ValueError("Git blob bytes differ from original")
            combined.update(restored)
            parts.append(
                {
                    "file": f"part{len(parts):03d}.bin",
                    "blob_id": blob,
                    "sha256": hashlib.sha256(restored).hexdigest(),
                    "bytes": len(restored),
                }
            )
    if sha(path) != before or combined.hexdigest() != before:
        raise ValueError("Original or reconstructed Git chunk bytes differ")
    return {
        "sha256": before,
        "bytes": path.stat().st_size,
        "parts": parts,
        "storage": "git_blobs_no_temporary_chunk_copy",
    }


def run(repo, data, output, parent, run_names, *, stream_chunks=False):
    if type(stream_chunks) is not bool:
        raise ValueError("Explicit boolean chunk mode required")
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

    def put_chunk(block):
        result = subprocess.run(
            [
                "git",
                "--git-dir=" + str(bare),
                "hash-object",
                "--no-filters",
                "-w",
                "--stdin",
            ],
            input=block,
            capture_output=True,
            check=True,
            env=env,
        )
        return result.stdout.decode("ascii").strip()

    def get_chunk(blob):
        return subprocess.run(
            ["git", "--git-dir=" + str(bare), "cat-file", "blob", blob],
            capture_output=True,
            check=True,
            env=env,
        ).stdout

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
            "source-control-screen-v1",
            "source-control-screen-v2",
            "source-control-screen-v3",
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
        "qa-sixhour-real-source-prepare-v1.xml",
        "qa-sixhour-real-source-prepare-v2.xml",
        "qa-sixhour-source-cold-combined-v1.xml",
        "qa-sixhour-source-transport-v1.xml",
        "qa-sixhour-source-subprocess-v1.xml",
        "qa-sixhour-backup-source-v1.xml",
        "qa-sixhour-palette-unit-v1.xml",
        "qa-sixhour-palette-unit-v2.xml",
        "qa-sixhour-palette-pipeline-v1.xml",
        "qa-sixhour-palette-pipeline-v2.xml",
        "qa-sixhour-palette-source-cold-v1.xml",
        "qa-sixhour-source-gallery-v1.xml",
        "qa-sixhour-stream-backup-v1.xml",
        "qa-sixhour-stream-backup-v2.xml",
        "qa-sixhour-independent-palette-unit-v1.xml",
        "qa-sixhour-independent-palette-pipeline-v1.xml",
        "qa-sixhour-source-metadata-v1.xml",
        "qa-sixhour-palette-full-regression-v1.xml",
        "qa-sixhour-palette-full-regression-v2.xml",
        "qa-sixhour-exposed-diagnostics-v1.xml",
        "qa-sixhour-diagnostic-backup-v1.xml",
        "qa-sixhour-diagnostic-backup-v2.xml",
        "qa-sixhour-diagnostic-backup-v3.xml",
        "qa-sixhour-aspect-unit-v1.xml",
        "qa-sixhour-aspect-unit-v2.xml",
        "qa-sixhour-aspect-pipeline-v1.xml",
        "qa-sixhour-aspect-contract-v1.xml",
        "qa-sixhour-aspect-full-regression-v1.xml",
        "qa-sixhour-third-source-transport-v1.xml",
        "qa-sixhour-paper-unit-v1.xml",
        "qa-sixhour-paper-pipeline-v1.xml",
        "qa-sixhour-paper-unit-v2.xml",
        "qa-sixhour-paper-contract-v1.xml",
        "qa-sixhour-strict-calibration-unit-v1.xml",
        "qa-sixhour-strict-calibration-pipeline-v1.xml",
        "qa-sixhour-strict-calibration-hostile-v1.xml",
        "qa-sixhour-paper-strict-full-regression-v1.xml",
    ):
        if (base / name).is_file():
            evidence.append((name, base / name))
    for name in (
        "source-controls-20261010-v1",
        "source-controls-20261010-v2",
        "source-controls-20261010-v3",
        "source-controls-20261010-v4",
        "source-controls-20261010-v5",
        "source-controls-20261010-v6",
        "source-controls-20261010-v7",
        "source-controls-20261010-v8",
        "source-controls-20261010-v9",
    ):
        root = base / name
        if not root.exists():
            continue
        receipt = json.loads((root / "preparation-receipt.json").read_text())
        if receipt["training_or_calibration"] or receipt["production_admitted"]:
            raise ValueError("Only preserved non-training source controls allowed")
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.is_symlink():
                raise ValueError("Only flat regular prepared-source evidence allowed")
            evidence.append((name + "/" + path.name, path))
    prefix = "learning_materials/visual_lexicon/backups/" + output.name + "/"
    manifest = []
    direct_blobs, direct_hashes, original_large = {}, {}, {}
    for name, path in evidence:
        record = {"file": name, "sha256": sha(path), "bytes": path.stat().st_size}
        if record["bytes"] > 32 * 1024 * 1024:
            if stream_chunks:
                record.update(git_chunks(path, put_chunk, get_chunk))
                original_large[path] = record["sha256"]
            else:
                destination = output / "chunks" / name
                record.update(chunks(path, destination))
            for part in record["parts"]:
                key = prefix + "chunks/" + name + "/" + part["file"]
                if stream_chunks:
                    direct_blobs[key], direct_hashes[key] = (
                        part["blob_id"],
                        part["sha256"],
                    )
                else:
                    files[key] = destination / part["file"]
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
    for name, blob in direct_blobs.items():
        if hashlib.sha256(get_chunk(blob)).hexdigest() != direct_hashes[name]:
            raise ValueError("Stored direct chunk changed before tree sealing")
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
        or not set(changed).issubset(set(files) | set(direct_blobs))
        or any(sha(files[n]) != h for n, h in hashes.items())
        or any(sha(path) != digest for path, digest in original_large.items())
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
        "source_sha256": {**hashes, **direct_hashes},
        "large_original_sha256": {
            str(path): digest for path, digest in original_large.items()
        },
        "stream_chunks": stream_chunks,
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
    parser.add_argument("--stream-chunks", action="store_true")
    args = parser.parse_args()
    run(
        args.repo.resolve(),
        args.data_root.resolve(),
        args.output.resolve(),
        args.expected_parent,
        args.run,
        stream_chunks=args.stream_chunks,
    )
