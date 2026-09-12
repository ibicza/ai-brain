"""In-process probes used by hermetic M-33.6k.5 exact quality."""

from __future__ import annotations

import argparse
import compileall
import os
import socket
import sys
from pathlib import Path


def _add_tool_handles(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--javac-executable", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--powershell-executable", type=Path)


def _bind_exact_tool_path(args: argparse.Namespace) -> None:
    handles = (
        args.git_executable,
        args.javac_executable,
        args.python_executable,
        args.powershell_executable,
    )
    directories: list[str] = []
    for handle in handles:
        if handle is None:
            continue
        directory = str(handle.resolve(strict=True).parent)
        if directory not in directories:
            directories.append(directory)
    os.environ["PATH"] = os.pathsep.join(directories)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    compile_command = commands.add_parser("compileall")
    compile_command.add_argument("--pycache-root", type=Path, required=True)
    compile_command.add_argument("paths", nargs="+")
    network = commands.add_parser("no-network")
    network.add_argument("--basetemp", type=Path, required=True)
    _add_tool_handles(network)
    pytest_command = commands.add_parser("pytest")
    _add_tool_handles(pytest_command)
    pytest_command.add_argument("pytest_arguments", nargs=argparse.REMAINDER)
    commands.add_parser("no-torch")
    commands.add_parser("route-preflight")
    args = parser.parse_args()
    if args.command == "compileall":
        cache = args.pycache_root.resolve(strict=False)
        if cache.exists():
            raise FileExistsError("M336K5 compile cache must be fresh")
        cache.parent.resolve(strict=True)
        cache.mkdir()
        sys.pycache_prefix = str(cache)
        passed = all(
            compileall.compile_dir(path, force=True, quiet=1) for path in args.paths
        )
        raise SystemExit(0 if passed else 1)
    if args.command == "no-network":
        import pytest

        _bind_exact_tool_path(args)

        def blocked(*_args, **_kwargs):
            raise AssertionError("network forbidden")

        socket.create_connection = blocked
        socket.socket.connect = blocked
        raise SystemExit(
            pytest.main(
                [
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "tmp_path_retention_policy=failed",
                    f"--basetemp={args.basetemp}",
                    "tests/test_m336k2_final_route.py",
                    "tests/test_m336k_candidate_isolation.py",
                ]
            )
        )
    if args.command == "pytest":
        import pytest

        _bind_exact_tool_path(args)
        arguments = list(args.pytest_arguments)
        if arguments[:1] == ["--"]:
            arguments.pop(0)
        raise SystemExit(pytest.main(arguments))
    if args.command == "no-torch":
        import ai_brain.stage3.acquisition.m336k2_stage  # noqa: F401

        raise SystemExit(1 if "torch" in sys.modules else 0)
    from ai_brain.stage3.acquisition.m336k2_controller import (
        build_m336k2_schema_registry,
    )
    from ai_brain.stage3.acquisition.m336k2_registry import (
        build_m336k2_route_registry,
    )

    registry = build_m336k2_route_registry(Path("."))
    schemas = build_m336k2_schema_registry()
    raise SystemExit(
        0
        if len(registry.components) >= 1 and schemas.incompatible_edge_count == 0
        else 1
    )


if __name__ == "__main__":
    main()
