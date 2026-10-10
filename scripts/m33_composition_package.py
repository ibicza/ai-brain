"""Hash-bound experiment capsule, without modifying Git HEAD or either index."""

import argparse
import ast
import hashlib
import io
import json
import tarfile
from pathlib import Path


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def script_dependencies(repo, names):
    """Include actual local script imports transitively, not workstation state."""
    selected, pending = set(names), list(names)
    while pending:
        name = pending.pop()
        tree = ast.parse((repo / name).read_text(encoding="utf-8-sig"), filename=name)
        for node in ast.walk(tree):
            modules = (
                [node.module]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            for module in modules:
                if not module:
                    continue
                relative = "scripts/" + module.replace(".", "/") + ".py"
                if (repo / relative).is_file() and relative not in selected:
                    selected.add(relative)
                    pending.append(relative)
    return sorted(selected)


def build(repo, output):
    if output.exists():
        raise ValueError("Fresh capsule required")
    sources = [
        (p, p.relative_to(repo).as_posix()) for p in (repo / "src").rglob("*.py")
    ]
    explicit = (
        "scripts/m33_composition_package.py",
        "scripts/m33_primary_composition_pilot.py",
        "scripts/m33_primary_relations_pilot.py",
        "scripts/m33_composition_verify.py",
        "scripts/m33_composition_control_screen.py",
        "scripts/m33_composition_background_probe.py",
        "scripts/m33_composition_rng_audit.py",
        "tests/test_primary_composition.py",
        "tests/test_primary_composition_pipeline.py",
        "tests/test_primary_composition_calibration.py",
        "tests/test_primary_composition_views.py",
        "tests/test_primary_composition_controls.py",
        "tests/test_primary_zero.py",
        "tests/test_primary_relations.py",
        "tests/test_primary_composition_package.py",
        "tests/test_primary_numeric_backend.py",
        "tests/test_primary_composition_backgrounds.py",
        "tests/conftest.py",
    )
    for name in script_dependencies(repo, explicit):
        sources.append((repo / name, name))
    manifest = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "x:gz") as archive:
        for path, relative in sorted(sources, key=lambda x: x[1]):
            before = sha(path)
            archive.add(path, arcname=relative, recursive=False)
            if sha(path) != before:
                raise ValueError("Source changed while copying")
            manifest.append({"file": relative, "sha256": before})
        blob = (
            json.dumps({"schema": 1, "files": manifest}, ensure_ascii=False, indent=2)
            + "\n"
        ).encode()
        info = tarfile.TarInfo("source-manifest.json")
        info.size = len(blob)
        archive.addfile(info, io.BytesIO(blob))
    with tarfile.open(output) as archive:
        for row in manifest:
            with archive.extractfile(row["file"]) as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("Capsule roundtrip failed")
    return {
        "capsule_sha256": sha(output),
        "files": len(manifest),
        "bytes": output.stat().st_size,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repo.resolve(), args.output.resolve())))
