"""Standard-library-only Python startup verification and exact dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import runpy
import site
import subprocess
import sys
from pathlib import Path


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _content_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _bytes_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_object(raw: bytes) -> dict:
    def pairs(rows: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in rows:
            if key in result:
                raise RuntimeError("M336K5 bootstrap input contains a duplicate key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise TypeError("M336K5 bootstrap input is not an object")
    return value


def _load_plan(args: argparse.Namespace) -> tuple[dict, bytes]:
    if (args.invocation_plan is None) == (args.inline_plan_json is None):
        raise RuntimeError("M336K5 bootstrap requires one invocation plan source")
    if args.invocation_plan is not None:
        raw = Path(args.invocation_plan).resolve(strict=True).read_bytes()
    else:
        raw = args.inline_plan_json.encode("utf-8")
    value = _strict_object(raw)
    body = dict(value)
    claimed = body.pop("invocation_plan_hash", None)
    if not isinstance(claimed, str) or _content_hash(body) != claimed:
        raise RuntimeError("M336K5 invocation plan hash changed")
    return value, raw


def _source_identity(repository: Path, git: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        (
            str(git.resolve(strict=True)),
            "-C",
            str(repository),
            "ls-files",
            "-z",
            "--",
            "src",
            "scripts",
            "tools",
            "schemas",
            "pyproject.toml",
            "uv.lock",
        ),
        check=True,
        capture_output=True,
        env=environment,
    )
    paths = sorted(
        (
            item.decode("utf-8", errors="strict")
            for item in result.stdout.split(b"\0")
            if item
        ),
        key=lambda item: item.encode("utf-8"),
    )
    if not paths:
        raise RuntimeError("M336K5 project source identity is empty")
    rows = []
    for relative in paths:
        path = repository.joinpath(*Path(relative).parts).resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(repository):
            raise RuntimeError("M336K5 tracked project source escaped checkout")
        rows.append([relative, _bytes_hash(path)])
    return _content_hash(rows)


def _normalized(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def _user_site_paths() -> tuple[str, ...]:
    value = site.getusersitepackages()
    rows = value if isinstance(value, (list, tuple)) else (value,)
    return tuple(_normalized(row) for row in rows if isinstance(row, str) and row)


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _verify_and_receipt(plan: dict) -> dict:
    policy = plan["startup_policy"]
    policy_body = dict(policy)
    policy_hash = policy_body.pop("policy_hash", None)
    environment = plan["sanitized_environment"]
    environment_body = dict(environment)
    environment_hash = environment_body.pop("environment_hash", None)
    expected_environment = dict(environment["variables"])
    actual_environment = dict(os.environ)
    if (
        policy_hash != _content_hash(policy_body)
        or environment_hash != _content_hash(environment_body)
        or environment["startup_policy_hash"] != policy_hash
        or actual_environment != expected_environment
    ):
        raise RuntimeError("M336K5 effective startup environment changed")
    for name in policy["forbidden_environment_names"]:
        if name in actual_environment:
            raise RuntimeError("M336K5 forbidden Python environment variable survived")
    python = Path(plan["python_executable"])
    bootstrap = Path(plan["bootstrap_script"]).resolve(strict=True)
    repository = Path(plan["repository"]).resolve(strict=True)
    git = Path(plan["git_executable"]).resolve(strict=True)
    project_source = _normalized(repository / "src")
    bootstrap_parent = _normalized(bootstrap.parent)
    standard_roots = tuple(
        _normalized(row)
        for row in (sys.base_prefix, sys.prefix, bootstrap_parent)
        if row
    )
    # A frozen interpreter may contain stale editable-install .pth entries or a
    # current-working-directory entry. Remove every path outside the exact
    # interpreter/bootstrap roots before the first project import, then add the
    # declared project source only after all startup invariants are verified.
    sys.path[:] = [
        row
        for row in sys.path
        if _normalized(row or os.curdir) != project_source
        and any(
            _is_under(_normalized(row or os.curdir), root) for root in standard_roots
        )
    ]
    target_kind = plan["target_kind"]
    target = plan["target"]
    if (
        _normalized(sys.executable) != _normalized(python)
        or _bytes_hash(python.resolve(strict=True))
        != plan["expected_python_executable_hash"]
        or platform.python_implementation() != plan["expected_python_implementation"]
        or platform.python_version() != plan["expected_python_version"]
        or _normalized(sys.prefix) != _normalized(plan["expected_environment_prefix"])
        or _bytes_hash(bootstrap) != plan["expected_bootstrap_source_hash"]
        or (
            target_kind == "SCRIPT"
            and _bytes_hash(Path(target).resolve(strict=True))
            != plan["expected_target_source_hash"]
        )
    ):
        raise RuntimeError("M336K5 interpreter/bootstrap/target binding changed")
    source_identity = _source_identity(repository, git, expected_environment)
    if source_identity != plan["expected_project_source_identity"]:
        raise RuntimeError("M336K5 project source identity changed")
    user_sites = _user_site_paths()
    path_rows = tuple(_normalized(row or os.curdir) for row in sys.path)
    user_site_membership = any(
        _is_under(row, user_site) for row in path_rows for user_site in user_sites
    )
    unsafe_paths = tuple(
        row
        for row in path_rows
        if any(_is_under(row, user_site) for user_site in user_sites)
        or not any(_is_under(row, root) for root in standard_roots)
    )
    forbidden_modules = (
        "ai_brain",
        "numpy",
        "tokenizers",
        "torch",
        "tree_sitter",
        "tree_sitter_java",
        "usercustomize",
    )
    unexpected_modules = tuple(
        name
        for name in sys.modules
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in forbidden_modules
        )
    )
    if "sitecustomize" in sys.modules:
        module = sys.modules["sitecustomize"]
        origin = getattr(module, "__file__", None)
        if origin is None or any(
            _is_under(_normalized(origin), user_site) for user_site in user_sites
        ):
            unexpected_modules += ("sitecustomize",)
    user_site_disabled = (
        os.environ.get("PYTHONNOUSERSITE") == "1"
        and sys.flags.no_user_site == 1
        and site.ENABLE_USER_SITE is False
        and not user_site_membership
    )
    if (
        not user_site_disabled
        or unsafe_paths
        or unexpected_modules
        or "torch" in sys.modules
    ):
        raise RuntimeError(
            "M336K5 effective Python startup state is unsafe: "
            f"user_site_disabled={user_site_disabled},"
            f"unsafe_path_count={len(unsafe_paths)},"
            f"unexpected_startup_module_count={len(unexpected_modules)},"
            f"torch_imported={'torch' in sys.modules}"
        )
    interpreter_binding_hash = _content_hash(
        {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable_hash": plan["expected_python_executable_hash"],
            "prefix_hash": hashlib.sha256(
                _normalized(sys.prefix).encode("utf-8")
            ).hexdigest(),
        }
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_PYTHON_STARTUP_RECEIPT",
        "startup_policy_hash": policy_hash,
        "interpreter_binding_hash": interpreter_binding_hash,
        "invocation_argument_hash": _content_hash(
            ["-s", "-B", "M336K5_STDLIB_BOOTSTRAP", "EXACT_INVOCATION_PLAN"]
        ),
        "sanitized_environment_hash": environment_hash,
        "project_source_identity": source_identity,
        "user_site_disabled_result": True,
        "python_no_user_site": sys.flags.no_user_site,
        "site_enable_user_site": bool(site.ENABLE_USER_SITE),
        "user_site_path_membership": user_site_membership,
        "unsafe_path_count": len(unsafe_paths),
        "unexpected_startup_module_count": len(unexpected_modules),
        "torch_imported": "torch" in sys.modules,
        "status": "PASS",
    }
    return {**body, "receipt_hash": _content_hash(body)}


def _write_receipt(path: Path, value: dict) -> None:
    destination = path.resolve(strict=False)
    if destination.exists():
        if destination.read_bytes() == (_canonical_json(value) + "\n").encode("utf-8"):
            return
        raise FileExistsError("M336K5 startup receipt output changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(_canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _path_identity(path: str | Path) -> str:
    return _content_hash(
        {
            "identity_kind": "NORMALIZED_ABSOLUTE_PRIVATE_PATH",
            "normalized_path": _normalized(path),
        }
    )


def _actual_launcher_receipt(
    *,
    plan: dict,
    raw_plan: bytes,
    plan_path: Path,
    operation: str,
    startup_receipt: dict,
    execution_scope: str,
) -> dict:
    selected_arguments = plan[f"{operation}_arguments"]
    policy = plan["startup_policy"]
    environment = plan["sanitized_environment"]
    body = {
        "schema_version": 1,
        "contract_role": "M336K13_ACTUAL_LAUNCHER_PLAN_RECEIPT",
        "execution_scope": execution_scope,
        "actual_invocation_plan_hash": plan["invocation_plan_hash"],
        "actual_plan_bytes_hash": hashlib.sha256(raw_plan).hexdigest(),
        "actual_plan_file_identity_hash": _path_identity(plan_path),
        "selected_operation": operation,
        "selected_target_kind": plan["target_kind"],
        "selected_target_source_hash": plan["expected_target_source_hash"],
        "selected_operation_argument_hash": _content_hash(selected_arguments),
        "startup_receipt_hash": startup_receipt["receipt_hash"],
        "startup_policy_hash": policy["policy_hash"],
        "sanitized_environment_hash": environment["environment_hash"],
        "project_source_identity_hash": plan["expected_project_source_identity"],
        "interpreter_binding_hash": startup_receipt["interpreter_binding_hash"],
        "outer_invocation_argument_hash": _content_hash(
            [
                "-s",
                "-B",
                _normalized(plan["bootstrap_script"]),
                "--invocation-plan",
                _normalized(plan_path),
                "--operation",
                operation,
            ]
        ),
        "forbidden_variable_occurrence_count": sum(
            name in os.environ for name in policy["forbidden_environment_names"]
        ),
        "unexpected_variable_count": len(
            set(os.environ) - {item[0] for item in environment["variables"]}
        ),
        "attestation_before_target_dispatch": True,
        "status": "PASS",
    }
    return {**body, "receipt_hash": _content_hash(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--invocation-plan")
    source.add_argument("--inline-plan-json")
    parser.add_argument("--operation", choices=("validate", "execute"), required=True)
    parser.add_argument("--actual-launcher-plan-receipt")
    parser.add_argument(
        "--execution-scope",
        choices=("OFFICIAL_CONTROLLER", "REHEARSAL"),
        default="OFFICIAL_CONTROLLER",
    )
    args = parser.parse_args()
    plan, raw_plan = _load_plan(args)
    receipt = _verify_and_receipt(plan)
    receipt_path = Path(plan[f"{args.operation}_startup_receipt"])
    _write_receipt(receipt_path, receipt)
    if args.actual_launcher_plan_receipt is not None:
        if args.invocation_plan is None:
            raise RuntimeError(
                "M336K13 actual launcher attestation requires a plan file"
            )
        actual_path = Path(args.actual_launcher_plan_receipt)
        bound_paths = {
            _normalized(args.invocation_plan),
            _normalized(plan["validate_arguments"][1]),
            _normalized(plan["validate_arguments"][4]),
            _normalized(plan["execute_arguments"][5]),
            _normalized(plan["validate_startup_receipt"]),
            _normalized(plan["execute_startup_receipt"]),
        }
        if not actual_path.is_absolute() or _normalized(actual_path) in bound_paths:
            raise RuntimeError(
                "M336K13 actual launcher receipt destination collides with a plan role"
            )
        actual = _actual_launcher_receipt(
            plan=plan,
            raw_plan=raw_plan,
            plan_path=Path(args.invocation_plan).resolve(strict=True),
            operation=args.operation,
            startup_receipt=receipt,
            execution_scope=args.execution_scope,
        )
        _write_receipt(actual_path, actual)
    repository = Path(plan["repository"]).resolve(strict=True)
    source_root = repository / "src"
    sys.path[:0] = [str(source_root), str(repository)]
    arguments = list(plan[f"{args.operation}_arguments"])
    if plan["process_role"] not in {
        "BUILD_HELPER",
        "EXACT_QUALITY",
        "GOLDEN_AUTHOR",
    }:
        arguments.extend(("--startup-receipt", str(receipt_path)))
    if args.actual_launcher_plan_receipt is not None:
        arguments.extend(
            (
                "--actual-launcher-plan-receipt",
                str(Path(args.actual_launcher_plan_receipt).resolve(strict=True)),
            )
        )
    sys.argv = [str(plan["target"]), *arguments]
    if plan["target_kind"] == "SCRIPT":
        runpy.run_path(
            str(Path(plan["target"]).resolve(strict=True)), run_name="__main__"
        )
    elif plan["target_kind"] == "MODULE":
        runpy.run_module(str(plan["target"]), run_name="__main__", alter_sys=True)
    else:
        raise RuntimeError("M336K5 bootstrap target kind changed")


if __name__ == "__main__":
    main()
