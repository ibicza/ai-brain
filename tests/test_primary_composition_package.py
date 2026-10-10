"""Source capsule must contain transitive script imports, not just local tests."""

import importlib.util
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "m33_composition_package", REPO / "scripts/m33_composition_package.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_full_capsule_can_import_legacy_test_dependencies_without_repo_scripts(
    tmp_path,
):
    capsule = tmp_path / "capsule.tgz"
    package.build(REPO, capsule)
    extracted = tmp_path / "isolated"
    extracted.mkdir()
    with tarfile.open(capsule) as archive:
        archive.extractall(extracted, filter="data")
    assert (extracted / "scripts/m33_primary_relations_pilot.py").is_file()
    assert (extracted / "scripts/m33_primary_zero_pilot.py").is_file()
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(str(extracted / p) for p in ("src", "scripts")),
    )
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import pathlib,m33_primary_relations_pilot as p,m33_primary_zero_pilot as z; assert pathlib.Path(p.__file__).parent == pathlib.Path('scripts').resolve(); assert pathlib.Path(z.__file__).parent == pathlib.Path('scripts').resolve()",
        ],
        cwd=extracted,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stderr


def test_script_dependency_closure_is_transitive_and_excludes_unimported_scripts(
    tmp_path,
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "first.py").write_text("import second\nimport os\n", encoding="utf-8")
    (scripts / "second.py").write_text("from third import value\n", encoding="utf-8")
    (scripts / "third.py").write_text("value=1\n", encoding="utf-8")
    (scripts / "unrelated.py").write_text(
        "raise RuntimeError('not in scope')\n", encoding="utf-8"
    )
    assert package.script_dependencies(tmp_path, ["scripts/first.py"]) == [
        "scripts/first.py",
        "scripts/second.py",
        "scripts/third.py",
    ]


def test_capsule_build_never_overwrites_prior_bytes(tmp_path):
    capsule = tmp_path / "capsule.tgz"
    capsule.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="Fresh"):
        package.build(REPO, capsule)
    assert capsule.read_bytes() == b"preserve"
