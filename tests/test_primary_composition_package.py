"""Source capsule must contain transitive script imports, not just local tests."""

import importlib.util
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

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
    assert (extracted / "scripts/m33_composition_remote.py").is_file()
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
    calibration = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_primary_composition_calibration.py",
            "--collect-only",
            "-q",
        ],
        cwd=extracted,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert calibration.returncode == 0, calibration.stderr + calibration.stdout
    assert "12 tests collected" in calibration.stdout


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


def test_remote_runtime_prefix_exposes_both_capsule_source_roots(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "composition_remote_under_test", REPO / "scripts/m33_composition_remote.py"
    )
    remote = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(remote)
    uploaded, commands = {}, []

    class StopBeforeExecution(Exception):
        pass

    class SFTP:
        def mkdir(self, path):
            pass

        def put(self, local, destination, confirm):
            assert confirm
            uploaded[destination] = Path(local).read_bytes()

        def open(self, destination, mode):
            assert mode == "rb"
            return io.BytesIO(uploaded[destination])

    class Client:
        def load_system_host_keys(self):
            pass

        def connect(self, *args, **kwargs):
            assert kwargs["allow_agent"] is False

        def open_sftp(self):
            return SFTP()

        def exec_command(self, command):
            commands.append(command)
            raise StopBeforeExecution

        def close(self):
            pass

    monkeypatch.setattr(remote.paramiko, "SSHClient", Client)
    previous, warm = tmp_path / "previous.pt", tmp_path / "warm.pt"
    previous.write_bytes(b"fixture-previous")
    warm.write_bytes(b"fixture-warm")
    args = SimpleNamespace(
        remote_name="m33-composition-20261010-v999",
        output=tmp_path / "run",
        repo=REPO,
        previous=previous,
        warm_candidate=warm,
        key=tmp_path / "not-used-no-network",
    )
    with pytest.raises(StopBeforeExecution):
        remote.run(args)
    assert len(commands) == 1
    assert " && PYTHONPATH=src:scripts AI_BRAIN_CAPSULE_SHA256=" in commands[0]
