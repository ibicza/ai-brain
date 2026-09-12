"""Build public, path-free startup/resource component receipts for M336K5."""

from __future__ import annotations

import argparse
from dataclasses import fields
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
    m336k5_karina_environment,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonStartupReceipt,
    build_m336k5_python_startup_policy,
    build_m336k5_sanitized_environment,
)


def _source_receipt(root: Path, relative: str, role: str) -> dict:
    path = root.joinpath(*relative.split("/")).resolve(strict=True)
    body = {
        "schema_version": 1,
        "contract_role": role,
        "repository_path": relative,
        "source_bytes_hash": bytes_hash(path.read_bytes()),
        "source_byte_count": path.stat().st_size,
    }
    return {**body, "receipt_hash": content_hash(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    git = args.git_executable.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() or output.is_relative_to(root):
        raise M336K2ProtocolError("M336K5 startup component output is unsafe")
    output.mkdir(parents=True)
    policy = build_m336k5_python_startup_policy()
    windows = build_m336k5_sanitized_environment(platform_role="WINDOWS")
    karina = build_m336k5_sanitized_environment(platform_role="KARINA")
    if karina.variables != m336k5_karina_environment():
        raise M336K2ProtocolError("M336K5 Karina startup policy diverged")
    project_source_identity = compute_m336j_project_source_identity(root, git)
    sanitized_body = {
        "schema_version": 1,
        "contract_role": "M336K5_PUBLIC_SANITIZED_ENVIRONMENT_POLICY",
        "startup_policy_hash": policy.policy_hash,
        "windows_environment_hash": windows.environment_hash,
        "karina_environment_hash": karina.environment_hash,
        "forbidden_environment_names": policy.forbidden_environment_names,
        "private_environment_values_published": False,
    }
    sanitized = {
        **sanitized_body,
        "receipt_hash": content_hash(sanitized_body),
    }
    environment_body = {
        "schema_version": 1,
        "contract_role": "M336K5_HERMETIC_PYTHON_ENVIRONMENT_MANIFEST",
        "startup_policy_hash": policy.policy_hash,
        "project_source_identity_hash": project_source_identity,
        "sanitized_environment_policy_hash": sanitized["receipt_hash"],
        "python_path_inherited": False,
        "python_home_inherited": False,
        "python_user_base_inherited": False,
        "user_site_effective_state_required": True,
        "torch_at_startup_allowed": False,
    }
    environment = {
        **environment_body,
        "environment_manifest_hash": content_hash(environment_body),
    }
    bootstrap = _source_receipt(
        root,
        "scripts/m336k5_python_bootstrap.py",
        "M336K5_STDLIB_BOOTSTRAP_SOURCE_RECEIPT",
    )
    launcher = _source_receipt(
        root,
        "scripts/m336k5_launch_python.ps1",
        "M336K5_WINDOWS_POWERSHELL_LAUNCHER_SOURCE_RECEIPT",
    )
    renderer_hash = bytes_hash(
        (root / "src/ai_brain/stage3/acquisition/m336j_execution.py").read_bytes()
    )
    karina_launcher_body = {
        "schema_version": 1,
        "contract_role": "M336K5_TYPED_KARINA_PYTHON_LAUNCHER",
        "startup_policy_hash": policy.policy_hash,
        "bootstrap_source_hash": bootstrap["source_bytes_hash"],
        "remote_command_renderer_source_hash": renderer_hash,
        "environment_clear_executable_role": "POSIX_ENVIRONMENT_CLEAR",
        "environment_clear_arguments": ("-i",),
        "python_arguments": ("-s", "-B"),
        "login_shell": False,
        "profile_startup": False,
        "bare_python_lookup": False,
    }
    karina_launcher = {
        **karina_launcher_body,
        "launcher_hash": content_hash(karina_launcher_body),
    }
    schema_body = {
        "schema_version": 1,
        "contract_role": "M336K5_PYTHON_STARTUP_RECEIPT_SCHEMA",
        "fields": tuple(field.name for field in fields(M336K5PythonStartupReceipt)),
        "additional_properties": False,
    }
    schema = {**schema_body, "schema_hash": content_hash(schema_body)}
    values = {
        "python_startup_policy": policy.canonical_object(),
        "python_environment_manifest": environment,
        "python_startup_bootstrap": bootstrap,
        "windows_python_launcher": launcher,
        "karina_python_launcher": karina_launcher,
        "sanitized_environment_policy": sanitized,
        "startup_receipt_schema": schema,
        "resource_monitor": _source_receipt(
            root,
            "src/ai_brain/stage3/acquisition/m336k5_resources.py",
            "M336K5_RESOURCE_MONITOR_SOURCE_RECEIPT",
        ),
        "cleanup_policy": _source_receipt(
            root,
            "src/ai_brain/stage3/acquisition/m336k5_cleanup.py",
            "M336K5_CLEANUP_POLICY_SOURCE_RECEIPT",
        ),
        "recovery_checkpoint_policy": _source_receipt(
            root,
            "src/ai_brain/stage3/acquisition/m336k5_recovery.py",
            "M336K5_RECOVERY_POLICY_SOURCE_RECEIPT",
        ),
    }
    for name, value in values.items():
        write_canonical_json(output / f"{name}.json", value)


if __name__ == "__main__":
    main()
