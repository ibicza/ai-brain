"""Canonical hermetic executable authority for M-33.6k.11.

The active v4 contracts deliberately keep static startup rules separate from the
effective sanitized environment.  Historical M336K2 manifests remain readable,
but only through an explicitly read-only loader that never consults ``os.environ``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2_COMMAND_EVENTS,
    M336K2_REQUIRED_EXECUTABLE_ROLES,
    M336K2ExecutableDependencyManifest,
    M336K2PrivateExecutionPlan,
    build_command_spec,
    build_m336k2_private_execution_plan,
    command_renderer_identity,
    verify_m336k2_executable_handles,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ExecutableBinding,
    M336K2ProtocolError,
    build_executable_binding,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonInvocationPlan,
    M336K5PythonStartupPolicy,
    M336K5PythonStartupReceipt,
    validate_m336k5_python_invocation,
    verify_m336k5_python_startup_policy,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    M336K10PostFreezeInputBundle,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)

M336K11_PROFILE_ID = "m336k8-final-v4"

OFFICIAL_CONTROLLER = "OFFICIAL_CONTROLLER"
PERSISTENT_KARINA_RUNTIME_CAPSULE = "PERSISTENT_KARINA_RUNTIME_CAPSULE"
REHEARSAL = "REHEARSAL"
SHARED_STATIC_POLICY = "SHARED_STATIC_POLICY"
HISTORICAL_READ_ONLY = "HISTORICAL_READ_ONLY"
M336K11_EXECUTABLE_SCOPES = frozenset(
    {
        OFFICIAL_CONTROLLER,
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        REHEARSAL,
        SHARED_STATIC_POLICY,
        HISTORICAL_READ_ONLY,
    }
)

M336K11_ACTIVE_EXECUTABLE_COMPONENTS = frozenset(
    {
        "controller_executable_dependency_manifest",
        "executable_dependency_manifest",
        "controller_python_environment_manifest",
        "python_environment_manifest",
        "controller_startup_binding",
        "effective_environment_binding",
        "execution_capsule_receipt",
        "route_manifest",
        "route_registry",
        "typed_route_manifest",
        "typed_route_registry",
        "native_route_manifest",
        "official_controller_executable_binding",
        "official_executable_binding_receipt",
    }
)
M336K11_PERSISTENT_EXECUTABLE_COMPONENTS = frozenset(
    {
        "persistent_capsule_python_environment_manifest",
        "persistent_capsule_executable_dependency_manifest",
        "persistent_capsule_source_binding",
        "capsule_binding_set",
        "capsule_liveness",
    }
)
M336K11_SHARED_EXECUTABLE_COMPONENTS = frozenset(
    {
        "python_startup_policy",
        "sanitized_environment_policy",
        "startup_receipt_schema",
        "python_startup_bootstrap",
        "windows_python_launcher",
    }
)


def m336k11_official_component_scopes() -> dict[str, str]:
    return {
        **{name: OFFICIAL_CONTROLLER for name in M336K11_ACTIVE_EXECUTABLE_COMPONENTS},
        **{
            name: PERSISTENT_KARINA_RUNTIME_CAPSULE
            for name in M336K11_PERSISTENT_EXECUTABLE_COMPONENTS
        },
        **{name: SHARED_STATIC_POLICY for name in M336K11_SHARED_EXECUTABLE_COMPONENTS},
    }


M336K11_MUTATION_CASES = (
    "temp-value-changed-static-policy-stable",
    "tmp-value-changed-static-policy-stable",
    "home-value-changed-static-policy-stable",
    "effective-environment-hash-kept-stale",
    "fixed-policy-value-changed",
    "pythonpath-added",
    "pythonhome-added",
    "pythonuserbase-added",
    "python-nousersite-removed",
    "user-site-enabled",
    "torch-imported-before-bootstrap",
    "f35-executable-manifest-in-v4",
    "f35-native-capsule-in-v4",
    "f35-native-route-in-v4",
    "stale-route-registry",
    "stale-stage-worker-bytes",
    "changed-command-renderer",
    "missing-required-executable-role",
    "extra-undeclared-executable-authority",
    "changed-executable-content-fully-rehashed",
    "changed-executable-path-fully-rehashed",
    "changed-executable-semantic-version-fully-rehashed",
    "controller-source-identity-changed",
    "controller-python-environment-changed",
    "startup-policy-changed-fully-rehashed",
    "sanitized-policy-changed-fully-rehashed",
    "active-alias-one-field-different",
    "historical-artifact-relabeled-official",
    "rehearsal-artifact-relabeled-official",
    "duplicate-active-executable-manifests",
    "executable-binding-receipt-forged-pass",
    "exact-launcher-parity-omitted",
    "startup-receipt-from-another-plan",
    "validate-controller-receipt-difference",
    "route-event-before-admissions",
    "raw-private-environment-value-published",
    "karina-capsule-rebound-to-windows-controller",
    "v3-profile-in-v4-authorization",
)


def _is_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _strict(value: Mapping[str, Any], cls: type, label: str) -> dict[str, Any]:
    expected = {field.name for field in fields(cls)}
    if type(value) is not dict or set(value) != expected:
        raise M336K2ProtocolError(f"M336K11 {label} fields changed")
    return dict(value)


def _hashed_body(value: Mapping[str, Any], field: str, label: str) -> str:
    body = dict(value)
    claimed = body.pop(field, None)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError(f"M336K11 {label} hash changed")
    return claimed


def _binding_from_dict(value: Mapping[str, Any]) -> M336K2ExecutableBinding:
    expected = set(M336K2ExecutableBinding.__dataclass_fields__)
    if type(value) is not dict or set(value) != expected:
        raise M336K2ProtocolError("M336K11 executable binding fields changed")
    arguments = value.get("version_arguments")
    if type(arguments) is not list:
        raise M336K2ProtocolError("M336K11 executable version arguments changed")
    binding = M336K2ExecutableBinding(
        **{**value, "version_arguments": tuple(arguments)}
    )
    body = asdict(binding)
    claimed = body.pop("binding_hash")
    if (
        binding.schema_version != 1
        or not binding.role
        or any(
            not _is_hash(item)
            for item in (
                binding.path_identity_hash,
                binding.file_sha256,
                binding.semantic_version_hash,
                binding.binding_hash,
            )
        )
        or not binding.semantic_version
        or binding.semantic_version_hash != content_hash(binding.semantic_version)
        or claimed != content_hash(body)
    ):
        raise M336K2ProtocolError("M336K11 executable binding is invalid")
    return binding


def _public_sanitized_environment_policy_hash(
    value: Mapping[str, Any], startup_policy: M336K5PythonStartupPolicy
) -> str:
    expected = {
        "schema_version",
        "contract_role",
        "startup_policy_hash",
        "windows_environment_hash",
        "karina_environment_hash",
        "forbidden_environment_names",
        "private_environment_values_published",
        "receipt_hash",
    }
    if type(value) is not dict or set(value) != expected:
        raise M336K2ProtocolError("M336K11 sanitized policy fields changed")
    policy_hash = _hashed_body(value, "receipt_hash", "sanitized policy")
    if (
        value["schema_version"] != 1
        or value["contract_role"] != "M336K5_PUBLIC_SANITIZED_ENVIRONMENT_POLICY"
        or value["startup_policy_hash"] != startup_policy.policy_hash
        or not _is_hash(value["windows_environment_hash"])
        or not _is_hash(value["karina_environment_hash"])
        or type(value["forbidden_environment_names"]) not in {list, tuple}
        or tuple(value["forbidden_environment_names"])
        != startup_policy.forbidden_environment_names
        or value["private_environment_values_published"] is not False
    ):
        raise M336K2ProtocolError("M336K11 sanitized policy is invalid")
    return policy_hash


@dataclass(frozen=True)
class M336K11HermeticExecutableDependencyManifest:
    schema_version: int
    contract_role: str
    execution_scope: str
    exact_implementation_tip: str
    bindings: tuple[M336K2ExecutableBinding, ...]
    python_invocation_handle_hash: str
    controller_python_environment_manifest_hash: str
    controller_source_identity_hash: str
    command_renderer_hash: str
    static_startup_policy_hash: str
    sanitized_environment_policy_hash: str
    expected_windows_sanitized_environment_hash: str
    startup_receipt_schema_hash: str
    bootstrap_source_hash: str
    windows_launcher_source_hash: str
    missing_required_role_count: int
    manifest_hash: str

    ROLE: ClassVar[str] = "M336K11_HERMETIC_EXECUTABLE_DEPENDENCY_MANIFEST_V2"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self) -> None:
        roles = tuple(item.role for item in self.bindings)
        for item in self.bindings:
            _binding_from_dict(
                {**asdict(item), "version_arguments": list(item.version_arguments)}
            )
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.execution_scope not in {OFFICIAL_CONTROLLER, REHEARSAL}
            or not _is_sha(self.exact_implementation_tip)
            or set(roles) != M336K2_REQUIRED_EXECUTABLE_ROLES
            or len(roles) != len(set(roles))
            or self.missing_required_role_count != 0
            or self.command_renderer_hash != command_renderer_identity()
            or any(not _is_hash(item) for item in hashes)
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K11 executable manifest is invalid")

    @classmethod
    def build(
        cls,
        *,
        executables: Mapping[str, tuple[Path, tuple[str, ...]]],
        python_invocation_handle: str,
        execution_scope: str,
        exact_implementation_tip: str,
        controller_python_environment_manifest_hash: str,
        controller_source_identity_hash: str,
        static_startup_policy_hash: str,
        sanitized_environment_policy_hash: str,
        expected_windows_sanitized_environment_hash: str,
        startup_receipt_schema_hash: str,
        bootstrap_source_hash: str,
        windows_launcher_source_hash: str,
    ) -> Self:
        if not python_invocation_handle:
            raise M336K2ProtocolError("M336K11 Python invocation handle is empty")
        roles = {role.casefold() for role in executables}
        bindings = tuple(
            build_executable_binding(path, role=role, version_arguments=arguments)
            for role, (path, arguments) in sorted(executables.items())
        )
        body = {
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "execution_scope": execution_scope,
            "exact_implementation_tip": exact_implementation_tip,
            "bindings": bindings,
            "python_invocation_handle_hash": content_hash(python_invocation_handle),
            "controller_python_environment_manifest_hash": (
                controller_python_environment_manifest_hash
            ),
            "controller_source_identity_hash": controller_source_identity_hash,
            "command_renderer_hash": command_renderer_identity(),
            "static_startup_policy_hash": static_startup_policy_hash,
            "sanitized_environment_policy_hash": sanitized_environment_policy_hash,
            "expected_windows_sanitized_environment_hash": (
                expected_windows_sanitized_environment_hash
            ),
            "startup_receipt_schema_hash": startup_receipt_schema_hash,
            "bootstrap_source_hash": bootstrap_source_hash,
            "windows_launcher_source_hash": windows_launcher_source_hash,
            "missing_required_role_count": len(
                M336K2_REQUIRED_EXECUTABLE_ROLES - roles
            ),
        }
        result = cls(**body, manifest_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        data = _strict(value, cls, "executable manifest")
        if type(data["bindings"]) is not list:
            raise M336K2ProtocolError("M336K11 executable bindings changed")
        result = cls(
            **{
                **data,
                "bindings": tuple(
                    _binding_from_dict(item) for item in data["bindings"]
                ),
            }
        )
        result.verify()
        return result


def load_historical_executable_components_read_only(
    value: Mapping[str, Any],
) -> M336K2ExecutableDependencyManifest:
    """Parse a v1 manifest without promoting it or reading the live environment."""

    expected = set(M336K2ExecutableDependencyManifest.__dataclass_fields__)
    if type(value) is not dict or set(value) != expected:
        raise M336K2ProtocolError("M336K11 historical executable fields changed")
    raw_bindings = value.get("bindings")
    if type(raw_bindings) is not list:
        raise M336K2ProtocolError("M336K11 historical executable bindings changed")
    parsed = M336K2ExecutableDependencyManifest(
        **{
            **value,
            "bindings": tuple(_binding_from_dict(item) for item in raw_bindings),
        }
    )
    body = asdict(parsed)
    claimed = body.pop("manifest_hash")
    if (
        parsed.schema_version != 1
        or parsed.contract_role != "M336K2_HERMETIC_EXECUTABLE_DEPENDENCY_MANIFEST"
        or parsed.missing_required_role_count != 0
        or {item.role for item in parsed.bindings} != M336K2_REQUIRED_EXECUTABLE_ROLES
        or any(
            not _is_hash(item)
            for item in (
                parsed.python_invocation_handle_hash,
                parsed.environment_identity_hash,
                parsed.source_identity_hash,
                parsed.command_renderer_hash,
                parsed.minimal_environment_policy_hash,
                parsed.manifest_hash,
            )
        )
        or claimed != content_hash(body)
    ):
        raise M336K2ProtocolError("M336K11 historical executable is invalid")
    return parsed


@dataclass(frozen=True)
class M336K11EffectiveEnvironmentBinding:
    schema_version: int
    contract_role: str
    execution_scope: str
    static_startup_policy_hash: str
    sanitized_environment_policy_hash: str
    expected_sanitized_environment_hash: str
    actual_startup_receipt_sanitized_environment_hash: str
    startup_receipt_hash: str
    interpreter_binding_hash: str
    invocation_argument_hash: str
    project_source_identity: str
    invocation_plan_hash: str
    forbidden_variable_occurrence_count: int
    unexpected_variable_count: int
    actual_environment_equals_invocation_plan: bool
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K11_EFFECTIVE_ENVIRONMENT_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash") or name == "project_source_identity"
        )
        passed = (
            self.expected_sanitized_environment_hash
            == self.actual_startup_receipt_sanitized_environment_hash
            and self.forbidden_variable_occurrence_count == 0
            and self.unexpected_variable_count == 0
            and self.actual_environment_equals_invocation_plan
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope not in {OFFICIAL_CONTROLLER, REHEARSAL}
            or any(not _is_hash(item) for item in hashes)
            or self.status != ("PASS" if passed else "FAIL")
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K11 effective environment is invalid")

    @classmethod
    def build(
        cls,
        *,
        plan: M336K5PythonInvocationPlan,
        startup_receipt: M336K5PythonStartupReceipt,
        sanitized_environment_policy_hash: str,
        execution_scope: str,
    ) -> Self:
        validate_m336k5_python_invocation(plan)
        startup = M336K5PythonStartupReceipt.from_dict(asdict(startup_receipt))
        forbidden = set(plan.startup_policy.forbidden_environment_names)
        actual_names = {name for name, _value in plan.sanitized_environment.variables}
        expected_names = set(plan.sanitized_environment.inherited_names)
        expected_names.update(name for name, _ in plan.startup_policy.fixed_environment)
        expected_names.update(
            name for name, _ in plan.startup_policy.windows_fixed_environment
        )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": execution_scope,
            "static_startup_policy_hash": plan.startup_policy.policy_hash,
            "sanitized_environment_policy_hash": sanitized_environment_policy_hash,
            "expected_sanitized_environment_hash": (
                plan.sanitized_environment.environment_hash
            ),
            "actual_startup_receipt_sanitized_environment_hash": (
                startup.sanitized_environment_hash
            ),
            "startup_receipt_hash": startup.receipt_hash,
            "interpreter_binding_hash": startup.interpreter_binding_hash,
            "invocation_argument_hash": startup.invocation_argument_hash,
            "project_source_identity": startup.project_source_identity,
            "invocation_plan_hash": plan.invocation_plan_hash,
            "forbidden_variable_occurrence_count": len(forbidden & actual_names),
            "unexpected_variable_count": len(actual_names - expected_names),
            "actual_environment_equals_invocation_plan": (
                startup.sanitized_environment_hash
                == plan.sanitized_environment.environment_hash
            ),
            "status": "PASS",
        }
        passed = (
            startup.startup_policy_hash == plan.startup_policy.policy_hash
            and startup.sanitized_environment_hash
            == plan.sanitized_environment.environment_hash
            and startup.project_source_identity == plan.expected_project_source_identity
            and not body["forbidden_variable_occurrence_count"]
            and not body["unexpected_variable_count"]
        )
        body["status"] = "PASS" if passed else "FAIL"
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "effective environment"))
        result.verify()
        return result


def m336k11_native_command_contract_hash(
    *,
    stage_worker_repository_path: str,
    stage_worker_bytes_hash: str,
    python_binding_hash: str,
    static_startup_policy_hash: str,
) -> str:
    return content_hash(
        (
            "m336k11.native-stage-command-contract.v1",
            stage_worker_repository_path,
            stage_worker_bytes_hash,
            python_binding_hash,
            static_startup_policy_hash,
            ("-s", "-B"),
            "argv-only",
            "shell-false",
        )
    )


def verify_m336k11_live_execution_inputs(
    *,
    manifest: M336K11HermeticExecutableDependencyManifest,
    effective_environment: M336K11EffectiveEnvironmentBinding,
    invocation_plan: M336K5PythonInvocationPlan,
    startup_receipt: M336K5PythonStartupReceipt,
    executable_handles: Mapping[str, Path],
    native_stage_worker_bytes: bytes,
    native_capsule: M336K11NativeExecutionCapsuleReceipt,
    expected_target: Path,
    controller_bootstrap_source_hash: str | None = None,
) -> None:
    """Match live launch inputs to the frozen v4 closure without environment reads."""

    manifest.verify()
    effective_environment.verify()
    native_capsule.verify()
    validate_m336k5_python_invocation(invocation_plan)
    startup = M336K5PythonStartupReceipt.from_dict(asdict(startup_receipt))
    if effective_environment.status != "PASS":
        raise M336K2ProtocolError("M336K11 effective environment did not pass")
    if controller_bootstrap_source_hash is not None and (
        not _is_hash(controller_bootstrap_source_hash)
        or not _is_hash(
            getattr(
                native_capsule,
                "final_controller_plan_binding_receipt_hash",
                None,
            )
        )
    ):
        raise M336K2ProtocolError("M336K13 controller bootstrap authority is invalid")
    if (
        invocation_plan.platform_role != "WINDOWS"
        or invocation_plan.target_kind != "SCRIPT"
        or Path(invocation_plan.target).resolve(strict=True)
        != expected_target.resolve(strict=True)
    ):
        raise M336K2ProtocolError("M336K11 invocation plan target changed")
    verify_m336k2_executable_handles(manifest, dict(executable_handles))
    relations = (
        (
            invocation_plan.invocation_plan_hash,
            effective_environment.invocation_plan_hash,
        ),
        (
            invocation_plan.startup_policy.policy_hash,
            manifest.static_startup_policy_hash,
        ),
        (
            invocation_plan.sanitized_environment.environment_hash,
            manifest.expected_windows_sanitized_environment_hash,
        ),
        (
            invocation_plan.expected_project_source_identity,
            manifest.controller_source_identity_hash,
        ),
        (
            content_hash(invocation_plan.python_executable),
            manifest.python_invocation_handle_hash,
        ),
        (
            invocation_plan.expected_bootstrap_source_hash,
            controller_bootstrap_source_hash or manifest.bootstrap_source_hash,
        ),
        (startup.startup_policy_hash, manifest.static_startup_policy_hash),
        (
            startup.sanitized_environment_hash,
            effective_environment.expected_sanitized_environment_hash,
        ),
        (
            startup.sanitized_environment_hash,
            effective_environment.actual_startup_receipt_sanitized_environment_hash,
        ),
        (startup.receipt_hash, effective_environment.startup_receipt_hash),
        (
            startup.interpreter_binding_hash,
            effective_environment.interpreter_binding_hash,
        ),
        (
            startup.invocation_argument_hash,
            effective_environment.invocation_argument_hash,
        ),
        (
            startup.project_source_identity,
            effective_environment.project_source_identity,
        ),
        (bytes_hash(native_stage_worker_bytes), native_capsule.stage_worker_bytes_hash),
    )
    if any(left != right for left, right in relations):
        raise M336K2ProtocolError("M336K11 live executable binding changed")


def build_m336k11_native_execution_plan(
    *,
    repository: Path,
    python_executable: Path,
    stage_request: Path,
    stage_receipt_root: Path,
    route_run_id: str,
    exact_f36_sha: str,
    route_registry_hash: str,
    dependency_manifest: M336K11HermeticExecutableDependencyManifest,
    effective_environment: M336K11EffectiveEnvironmentBinding,
    capsule: M336K11NativeExecutionCapsuleReceipt,
) -> M336K2PrivateExecutionPlan:
    """Render the active v4 native plan from its canonical frozen binding."""

    root = repository.resolve(strict=True)
    python = python_executable.resolve(strict=True)
    request = stage_request.resolve(strict=True)
    receipts = stage_receipt_root.resolve(strict=False)
    dependency_manifest.verify()
    effective_environment.verify()
    capsule.verify()
    if effective_environment.status != "PASS":
        raise M336K2ProtocolError("M336K11 effective environment did not pass")
    python_bindings = tuple(
        item for item in dependency_manifest.bindings if item.role == "python"
    )
    if len(python_bindings) != 1:
        raise M336K2ProtocolError("M336K11 Python executable authority changed")
    python_binding = python_bindings[0]
    worker = root.joinpath(*capsule.stage_worker_repository_path.split("/"))
    expected_command = m336k11_native_command_contract_hash(
        stage_worker_repository_path=capsule.stage_worker_repository_path,
        stage_worker_bytes_hash=capsule.stage_worker_bytes_hash,
        python_binding_hash=python_binding.binding_hash,
        static_startup_policy_hash=dependency_manifest.static_startup_policy_hash,
    )
    relations = (
        (bytes_hash(python.read_bytes()), python_binding.file_sha256),
        (content_hash(python.as_posix()), python_binding.path_identity_hash),
        (
            capsule.exact_implementation_tip,
            dependency_manifest.exact_implementation_tip,
        ),
        (capsule.route_registry_hash, route_registry_hash),
        (
            capsule.executable_dependency_manifest_hash,
            dependency_manifest.manifest_hash,
        ),
        (
            capsule.effective_environment_binding_receipt_hash,
            effective_environment.receipt_hash,
        ),
        (capsule.stage_worker_bytes_hash, bytes_hash(worker.read_bytes())),
        (capsule.python_binding_hash, python_binding.binding_hash),
        (capsule.command_contract_hash, expected_command),
        (capsule.command_renderer_hash, dependency_manifest.command_renderer_hash),
        (
            capsule.static_startup_policy_hash,
            dependency_manifest.static_startup_policy_hash,
        ),
        (
            capsule.sanitized_environment_policy_hash,
            dependency_manifest.sanitized_environment_policy_hash,
        ),
        (
            capsule.expected_windows_sanitized_environment_hash,
            dependency_manifest.expected_windows_sanitized_environment_hash,
        ),
    )
    if any(left != right for left, right in relations):
        raise M336K2ProtocolError("M336K11 native command contract changed")
    commands = tuple(
        build_command_spec(
            event=event,
            executable=python,
            arguments=(
                "-s",
                "-B",
                str(worker),
                "--request",
                str(request),
                "--event",
                event,
                "--receipt",
                str(receipts / f"{event}.json"),
            ),
            working_directory=root,
            receipt_path=receipts / f"{event}.json",
            receipt_hash_field="receipt_hash",
            expected_status="PASS",
        )
        for event in M336K2_COMMAND_EVENTS
    )
    return build_m336k2_private_execution_plan(
        route_run_id=route_run_id,
        exact_f28_sha=exact_f36_sha,
        route_registry_hash=route_registry_hash,
        commands=commands,
    )


@dataclass(frozen=True)
class M336K11NativeExecutionCapsuleReceipt:
    schema_version: int
    contract_role: str
    execution_scope: str
    exact_implementation_tip: str
    route_registry_hash: str
    typed_route_manifest_hash: str
    executable_dependency_manifest_hash: str
    effective_environment_binding_receipt_hash: str
    stage_worker_repository_path: str
    stage_worker_bytes_hash: str
    python_binding_hash: str
    command_contract_hash: str
    command_renderer_hash: str
    static_startup_policy_hash: str
    sanitized_environment_policy_hash: str
    expected_windows_sanitized_environment_hash: str
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K11_NATIVE_EXECUTION_CAPSULE_RECEIPT_V2"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        expected_command = m336k11_native_command_contract_hash(
            stage_worker_repository_path=self.stage_worker_repository_path,
            stage_worker_bytes_hash=self.stage_worker_bytes_hash,
            python_binding_hash=self.python_binding_hash,
            static_startup_policy_hash=self.static_startup_policy_hash,
        )
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.execution_scope not in {OFFICIAL_CONTROLLER, REHEARSAL}
            or not _is_sha(self.exact_implementation_tip)
            or self.stage_worker_repository_path != "scripts/m336k2_run_stage.py"
            or any(not _is_hash(item) for item in hashes)
            or self.command_contract_hash != expected_command
            or self.command_renderer_hash != command_renderer_identity()
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K11 native execution capsule is invalid")

    @classmethod
    def build(
        cls,
        *,
        repository: Path,
        route_registry_hash: str,
        typed_route_manifest_hash: str,
        dependency_manifest: M336K11HermeticExecutableDependencyManifest,
        effective_environment: M336K11EffectiveEnvironmentBinding,
    ) -> Self:
        dependency_manifest.verify()
        effective_environment.verify()
        if (
            dependency_manifest.execution_scope != effective_environment.execution_scope
            or effective_environment.status != "PASS"
        ):
            raise M336K2ProtocolError("M336K11 native capsule scope changed")
        worker_relative = "scripts/m336k2_run_stage.py"
        worker_hash = bytes_hash(
            repository.resolve(strict=True)
            .joinpath(*worker_relative.split("/"))
            .read_bytes()
        )
        python_bindings = tuple(
            item for item in dependency_manifest.bindings if item.role == "python"
        )
        if len(python_bindings) != 1:
            raise M336K2ProtocolError("M336K11 Python binding changed")
        body = {
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "execution_scope": dependency_manifest.execution_scope,
            "exact_implementation_tip": dependency_manifest.exact_implementation_tip,
            "route_registry_hash": route_registry_hash,
            "typed_route_manifest_hash": typed_route_manifest_hash,
            "executable_dependency_manifest_hash": dependency_manifest.manifest_hash,
            "effective_environment_binding_receipt_hash": (
                effective_environment.receipt_hash
            ),
            "stage_worker_repository_path": worker_relative,
            "stage_worker_bytes_hash": worker_hash,
            "python_binding_hash": python_bindings[0].binding_hash,
            "command_contract_hash": m336k11_native_command_contract_hash(
                stage_worker_repository_path=worker_relative,
                stage_worker_bytes_hash=worker_hash,
                python_binding_hash=python_bindings[0].binding_hash,
                static_startup_policy_hash=(
                    dependency_manifest.static_startup_policy_hash
                ),
            ),
            "command_renderer_hash": dependency_manifest.command_renderer_hash,
            "static_startup_policy_hash": (
                dependency_manifest.static_startup_policy_hash
            ),
            "sanitized_environment_policy_hash": (
                dependency_manifest.sanitized_environment_policy_hash
            ),
            "expected_windows_sanitized_environment_hash": (
                dependency_manifest.expected_windows_sanitized_environment_hash
            ),
            "status": "PASS",
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "native capsule"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K11OfficialControllerExecutableBinding:
    schema_version: int
    contract_role: str
    execution_scope: str
    official_profile_id: str
    official_profile_hash: str
    exact_implementation_tip: str
    controller_source_identity_receipt_hash: str
    controller_source_identity_hash: str
    controller_python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    static_startup_policy_hash: str
    sanitized_environment_policy_hash: str
    expected_windows_sanitized_environment_hash: str
    startup_receipt_schema_hash: str
    bootstrap_source_hash: str
    windows_launcher_source_hash: str
    route_registry_hash: str
    typed_route_manifest_hash: str
    native_stage_worker_source_hash: str
    command_renderer_hash: str
    native_command_contract_hash: str
    effective_environment_binding_receipt_hash: str
    binding_hash: str

    ROLE: ClassVar[str] = "M336K11_OFFICIAL_CONTROLLER_EXECUTABLE_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_hash": self.binding_hash}

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != OFFICIAL_CONTROLLER
            or self.official_profile_id != M336K11_PROFILE_ID
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
            or self.official_profile_hash != profile.profile_hash
            or not _is_sha(self.exact_implementation_tip)
            or any(not _is_hash(item) for item in hashes)
            or self.command_renderer_hash != command_renderer_identity()
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K11 official executable binding is invalid")

    @classmethod
    def build(
        cls,
        *,
        profile: M336KOfficialRouteProfile,
        source_identity_receipt_hash: str,
        source_identity_hash: str,
        environment_manifest_hash: str,
        manifest: M336K11HermeticExecutableDependencyManifest,
        effective_environment: M336K11EffectiveEnvironmentBinding,
        route_registry_hash: str,
        typed_route_manifest_hash: str,
        native_stage_worker_source_hash: str,
        native_command_contract_hash: str,
    ) -> Self:
        profile.verify()
        manifest.verify()
        effective_environment.verify()
        if (
            manifest.execution_scope != OFFICIAL_CONTROLLER
            or effective_environment.execution_scope != OFFICIAL_CONTROLLER
            or effective_environment.status != "PASS"
        ):
            raise M336K2ProtocolError("M336K11 official executable input changed")
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": OFFICIAL_CONTROLLER,
            "official_profile_id": profile.profile_id,
            "official_profile_hash": profile.profile_hash,
            "exact_implementation_tip": manifest.exact_implementation_tip,
            "controller_source_identity_receipt_hash": source_identity_receipt_hash,
            "controller_source_identity_hash": source_identity_hash,
            "controller_python_environment_manifest_hash": environment_manifest_hash,
            "executable_dependency_manifest_hash": manifest.manifest_hash,
            "static_startup_policy_hash": manifest.static_startup_policy_hash,
            "sanitized_environment_policy_hash": (
                manifest.sanitized_environment_policy_hash
            ),
            "expected_windows_sanitized_environment_hash": (
                manifest.expected_windows_sanitized_environment_hash
            ),
            "startup_receipt_schema_hash": manifest.startup_receipt_schema_hash,
            "bootstrap_source_hash": manifest.bootstrap_source_hash,
            "windows_launcher_source_hash": manifest.windows_launcher_source_hash,
            "route_registry_hash": route_registry_hash,
            "typed_route_manifest_hash": typed_route_manifest_hash,
            "native_stage_worker_source_hash": native_stage_worker_source_hash,
            "command_renderer_hash": manifest.command_renderer_hash,
            "native_command_contract_hash": native_command_contract_hash,
            "effective_environment_binding_receipt_hash": (
                effective_environment.receipt_hash
            ),
        }
        result = cls(**body, binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "official executable binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K11NativeRouteManifest:
    schema_version: int
    contract_role: str
    execution_scope: str
    route_version: str
    official_profile_id: str
    official_profile_hash: str
    route_registry_hash: str
    typed_route_manifest_hash: str
    executable_dependency_manifest_hash: str
    effective_environment_binding_receipt_hash: str
    native_execution_capsule_receipt_hash: str
    static_startup_policy_hash: str
    sanitized_environment_policy_hash: str
    expected_windows_sanitized_environment_hash: str
    status: str
    manifest_hash: str

    ROLE: ClassVar[str] = "M336K11_ACTIVE_NATIVE_ROUTE_MANIFEST"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != OFFICIAL_CONTROLLER
            or self.official_profile_id != M336K11_PROFILE_ID
            or self.official_profile_hash != profile.profile_hash
            or self.route_version != profile.route_version
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.status != "PASS"
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K11 active native route is invalid")

    @classmethod
    def build(
        cls,
        *,
        profile: M336KOfficialRouteProfile,
        binding: M336K11OfficialControllerExecutableBinding,
        capsule: M336K11NativeExecutionCapsuleReceipt,
    ) -> Self:
        profile.verify()
        binding.verify()
        capsule.verify()
        if capsule.execution_scope != OFFICIAL_CONTROLLER:
            raise M336K2ProtocolError("M336K11 active native route scope changed")
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": OFFICIAL_CONTROLLER,
            "route_version": profile.route_version,
            "official_profile_id": profile.profile_id,
            "official_profile_hash": profile.profile_hash,
            "route_registry_hash": binding.route_registry_hash,
            "typed_route_manifest_hash": binding.typed_route_manifest_hash,
            "executable_dependency_manifest_hash": (
                binding.executable_dependency_manifest_hash
            ),
            "effective_environment_binding_receipt_hash": (
                binding.effective_environment_binding_receipt_hash
            ),
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "static_startup_policy_hash": binding.static_startup_policy_hash,
            "sanitized_environment_policy_hash": (
                binding.sanitized_environment_policy_hash
            ),
            "expected_windows_sanitized_environment_hash": (
                binding.expected_windows_sanitized_environment_hash
            ),
            "status": "PASS",
        }
        result = cls(**body, manifest_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "active native route"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K11OfficialExecutableBindingReceipt:
    schema_version: int
    contract_role: str
    controller_source_identity_hash: str
    controller_python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    static_startup_policy_hash: str
    sanitized_environment_policy_hash: str
    expected_windows_environment_hash: str
    effective_environment_binding_receipt_hash: str
    controller_startup_binding_hash: str
    native_execution_capsule_receipt_hash: str
    current_route_registry_hash: str
    current_route_manifest_hash: str
    stage_worker_source_hash: str
    command_contract_hash: str
    official_controller_executable_binding_hash: str
    final_authorization_hash: str
    post_freeze_input_bundle_hash: str
    final_request_hash: str
    component_scope_manifest_hash: str
    active_alias_byte_difference_count: int
    executable_semantic_mismatch_count: int
    historical_component_in_active_scope_count: int
    rehearsal_component_in_active_scope_count: int
    duplicate_active_manifest_authority_count: int
    unscoped_executable_component_count: int
    legacy_copied_active_executable_component_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K11_OFFICIAL_EXECUTABLE_BINDING_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        failures = (
            self.active_alias_byte_difference_count,
            self.executable_semantic_mismatch_count,
            self.historical_component_in_active_scope_count,
            self.rehearsal_component_in_active_scope_count,
            self.duplicate_active_manifest_authority_count,
            self.unscoped_executable_component_count,
            self.legacy_copied_active_executable_component_count,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or any(type(value) is not int or value < 0 for value in failures)
            or self.status != "PASS"
            or any(failures)
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K11 executable binding receipt is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "executable binding receipt"))
        result.verify()
        return result


def verify_m336k11_official_executable_binding(
    *,
    binding: M336K11OfficialControllerExecutableBinding,
    manifest: M336K11HermeticExecutableDependencyManifest,
    active_alias_bytes: bytes,
    canonical_manifest_bytes: bytes,
    startup_policy: M336K5PythonStartupPolicy,
    sanitized_environment_policy: Mapping[str, Any],
    controller_environment_manifest: Mapping[str, Any],
    controller_source_identity: Mapping[str, Any],
    effective_environment: M336K11EffectiveEnvironmentBinding,
    controller_startup_binding: Mapping[str, Any],
    native_capsule: M336K11NativeExecutionCapsuleReceipt,
    native_route: M336K11NativeRouteManifest,
    route_registry: Mapping[str, Any],
    typed_route_manifest: Mapping[str, Any],
    final_authorization: Mapping[str, Any],
    post_freeze_input_bundle: Mapping[str, Any],
    final_request: Mapping[str, Any],
    component_scopes: Mapping[str, str],
    invocation_plan: M336K5PythonInvocationPlan,
    startup_receipt: M336K5PythonStartupReceipt,
    executable_handles: Mapping[str, Path],
    native_stage_worker_bytes: bytes,
    expected_target: Path,
    historical_copied_names: frozenset[str] = frozenset(),
) -> M336K11OfficialExecutableBindingReceipt:
    """Verify the complete active v4 executable graph without side effects."""

    binding.verify()
    manifest.verify()
    effective_environment.verify()
    native_capsule.verify()
    native_route.verify()
    verify_m336k5_python_startup_policy(startup_policy)
    verify_m336k11_live_execution_inputs(
        manifest=manifest,
        effective_environment=effective_environment,
        invocation_plan=invocation_plan,
        startup_receipt=startup_receipt,
        executable_handles=executable_handles,
        native_stage_worker_bytes=native_stage_worker_bytes,
        native_capsule=native_capsule,
        expected_target=expected_target,
    )
    sanitized_hash = _public_sanitized_environment_policy_hash(
        sanitized_environment_policy, startup_policy
    )
    environment_hash = _hashed_body(
        controller_environment_manifest,
        "environment_manifest_hash",
        "controller environment",
    )
    source_receipt_hash = _hashed_body(
        controller_source_identity, "receipt_hash", "controller source identity"
    )
    registry_hash = _hashed_body(route_registry, "registry_hash", "route registry")
    route_hash = _hashed_body(
        typed_route_manifest, "manifest_hash", "typed route manifest"
    )
    authorization_hash = _hashed_body(
        final_authorization, "authorization_hash", "final authorization"
    )
    post_hash = _hashed_body(
        post_freeze_input_bundle, "bundle_hash", "post-freeze bundle"
    )
    request_hash_field = (
        "request_binding_hash"
        if "request_binding_hash" in final_request
        else "request_hash"
    )
    request_hash = _hashed_body(
        final_request, request_hash_field, "final request binding"
    )
    startup_binding_hash = _hashed_body(
        controller_startup_binding, "binding_hash", "controller startup binding"
    )
    source_identity_hash = controller_source_identity.get(
        "live_project_source_identity"
    )
    expected_environment_hash = sanitized_environment_policy.get(
        "windows_environment_hash"
    )
    expected_relations = (
        (binding.exact_implementation_tip, manifest.exact_implementation_tip),
        (binding.controller_source_identity_receipt_hash, source_receipt_hash),
        (binding.controller_source_identity_hash, source_identity_hash),
        (binding.controller_python_environment_manifest_hash, environment_hash),
        (binding.executable_dependency_manifest_hash, manifest.manifest_hash),
        (binding.static_startup_policy_hash, startup_policy.policy_hash),
        (binding.sanitized_environment_policy_hash, sanitized_hash),
        (
            binding.expected_windows_sanitized_environment_hash,
            expected_environment_hash,
        ),
        (
            binding.effective_environment_binding_receipt_hash,
            effective_environment.receipt_hash,
        ),
        (binding.route_registry_hash, registry_hash),
        (binding.typed_route_manifest_hash, route_hash),
        (manifest.controller_python_environment_manifest_hash, environment_hash),
        (manifest.controller_source_identity_hash, source_identity_hash),
        (manifest.static_startup_policy_hash, startup_policy.policy_hash),
        (manifest.sanitized_environment_policy_hash, sanitized_hash),
        (
            manifest.expected_windows_sanitized_environment_hash,
            expected_environment_hash,
        ),
        (manifest.startup_receipt_schema_hash, binding.startup_receipt_schema_hash),
        (manifest.bootstrap_source_hash, binding.bootstrap_source_hash),
        (manifest.windows_launcher_source_hash, binding.windows_launcher_source_hash),
        (effective_environment.static_startup_policy_hash, startup_policy.policy_hash),
        (effective_environment.sanitized_environment_policy_hash, sanitized_hash),
        (
            effective_environment.expected_sanitized_environment_hash,
            expected_environment_hash,
        ),
        (native_capsule.executable_dependency_manifest_hash, manifest.manifest_hash),
        (
            native_capsule.effective_environment_binding_receipt_hash,
            effective_environment.receipt_hash,
        ),
        (native_capsule.route_registry_hash, registry_hash),
        (native_capsule.typed_route_manifest_hash, route_hash),
        (
            native_capsule.stage_worker_bytes_hash,
            binding.native_stage_worker_source_hash,
        ),
        (native_capsule.command_contract_hash, binding.native_command_contract_hash),
        (native_capsule.exact_implementation_tip, manifest.exact_implementation_tip),
        (native_capsule.static_startup_policy_hash, startup_policy.policy_hash),
        (native_capsule.sanitized_environment_policy_hash, sanitized_hash),
        (
            native_capsule.expected_windows_sanitized_environment_hash,
            expected_environment_hash,
        ),
        (native_route.executable_dependency_manifest_hash, manifest.manifest_hash),
        (
            native_route.native_execution_capsule_receipt_hash,
            native_capsule.receipt_hash,
        ),
        (
            native_route.effective_environment_binding_receipt_hash,
            effective_environment.receipt_hash,
        ),
        (native_route.static_startup_policy_hash, startup_policy.policy_hash),
        (native_route.sanitized_environment_policy_hash, sanitized_hash),
        (
            native_route.expected_windows_sanitized_environment_hash,
            expected_environment_hash,
        ),
        (
            controller_startup_binding.get(
                "controller_executable_dependency_manifest_hash"
            ),
            manifest.manifest_hash,
        ),
        (
            controller_startup_binding.get("startup_policy_hash"),
            startup_policy.policy_hash,
        ),
        (
            controller_startup_binding.get("sanitized_environment_policy_hash"),
            sanitized_hash,
        ),
        (
            controller_startup_binding.get("startup_receipt_schema_hash"),
            manifest.startup_receipt_schema_hash,
        ),
        (
            controller_startup_binding.get("bootstrap_source_hash"),
            manifest.bootstrap_source_hash,
        ),
        (
            controller_startup_binding.get("windows_launcher_source_hash"),
            manifest.windows_launcher_source_hash,
        ),
        (
            final_authorization.get("executable_dependency_manifest_hash"),
            manifest.manifest_hash,
        ),
        (
            final_authorization.get("official_controller_executable_binding_hash"),
            binding.binding_hash,
        ),
        (
            final_authorization.get("official_executable_binding_receipt_hash"),
            binding.binding_hash,
        ),
        (
            post_freeze_input_bundle.get(
                "controller_executable_dependency_manifest_hash"
            ),
            manifest.manifest_hash,
        ),
        (
            post_freeze_input_bundle.get("official_controller_executable_binding_hash"),
            binding.binding_hash,
        ),
        (
            post_freeze_input_bundle.get("effective_environment_binding_receipt_hash"),
            effective_environment.receipt_hash,
        ),
        (
            post_freeze_input_bundle.get("native_execution_capsule_receipt_hash"),
            native_capsule.receipt_hash,
        ),
        (
            post_freeze_input_bundle.get("native_route_manifest_hash"),
            native_route.manifest_hash,
        ),
        (
            post_freeze_input_bundle.get("official_executable_binding_receipt_hash"),
            binding.binding_hash,
        ),
        (
            final_request.get("official_controller_executable_binding_hash"),
            binding.binding_hash,
        ),
    )
    mismatches = sum(left != right for left, right in expected_relations)
    mismatches += sum(
        (
            manifest.execution_scope != OFFICIAL_CONTROLLER,
            effective_environment.execution_scope != OFFICIAL_CONTROLLER,
            effective_environment.status != "PASS",
            native_capsule.execution_scope != OFFICIAL_CONTROLLER,
            binding.execution_scope != OFFICIAL_CONTROLLER,
            native_route.execution_scope != OFFICIAL_CONTROLLER,
        )
    )
    mismatches += sum(
        name in M336K11_PERSISTENT_EXECUTABLE_COMPONENTS
        and scope != PERSISTENT_KARINA_RUNTIME_CAPSULE
        for name, scope in component_scopes.items()
    )
    mismatches += sum(
        name in M336K11_ACTIVE_EXECUTABLE_COMPONENTS and scope != OFFICIAL_CONTROLLER
        for name, scope in component_scopes.items()
    )
    mismatches += sum(
        name in M336K11_SHARED_EXECUTABLE_COMPONENTS and scope != SHARED_STATIC_POLICY
        for name, scope in component_scopes.items()
    )
    active_alias_difference = int(active_alias_bytes != canonical_manifest_bytes)
    managed_components = (
        M336K11_ACTIVE_EXECUTABLE_COMPONENTS
        | M336K11_PERSISTENT_EXECUTABLE_COMPONENTS
        | M336K11_SHARED_EXECUTABLE_COMPONENTS
    )
    unscoped = len(managed_components - set(component_scopes)) + len(
        set(component_scopes) - managed_components
    )
    unscoped += sum(
        scope not in M336K11_EXECUTABLE_SCOPES for scope in component_scopes.values()
    )
    historical_active = sum(
        name in M336K11_ACTIVE_EXECUTABLE_COMPONENTS and scope == HISTORICAL_READ_ONLY
        for name, scope in component_scopes.items()
    )
    rehearsal_active = sum(
        name in M336K11_ACTIVE_EXECUTABLE_COMPONENTS and scope == REHEARSAL
        for name, scope in component_scopes.items()
    )
    manifest_authorities = sum(
        name.endswith("executable_dependency_manifest") and scope == OFFICIAL_CONTROLLER
        for name, scope in component_scopes.items()
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K11OfficialExecutableBindingReceipt.ROLE,
        "controller_source_identity_hash": binding.controller_source_identity_hash,
        "controller_python_environment_manifest_hash": environment_hash,
        "executable_dependency_manifest_hash": manifest.manifest_hash,
        "static_startup_policy_hash": startup_policy.policy_hash,
        "sanitized_environment_policy_hash": sanitized_hash,
        "expected_windows_environment_hash": expected_environment_hash,
        "effective_environment_binding_receipt_hash": effective_environment.receipt_hash,
        "controller_startup_binding_hash": startup_binding_hash,
        "native_execution_capsule_receipt_hash": native_capsule.receipt_hash,
        "current_route_registry_hash": registry_hash,
        "current_route_manifest_hash": route_hash,
        "stage_worker_source_hash": native_capsule.stage_worker_bytes_hash,
        "command_contract_hash": native_capsule.command_contract_hash,
        "official_controller_executable_binding_hash": binding.binding_hash,
        "final_authorization_hash": authorization_hash,
        "post_freeze_input_bundle_hash": post_hash,
        "final_request_hash": request_hash,
        "component_scope_manifest_hash": content_hash(
            tuple(sorted(component_scopes.items()))
        ),
        "active_alias_byte_difference_count": active_alias_difference,
        "executable_semantic_mismatch_count": mismatches,
        "historical_component_in_active_scope_count": historical_active,
        "rehearsal_component_in_active_scope_count": rehearsal_active,
        "duplicate_active_manifest_authority_count": max(manifest_authorities - 2, 0),
        "unscoped_executable_component_count": unscoped,
        "legacy_copied_active_executable_component_count": len(
            historical_copied_names & M336K11_ACTIVE_EXECUTABLE_COMPONENTS
        ),
    }
    failures = tuple(value for name, value in body.items() if name.endswith("_count"))
    body["status"] = "PASS" if not any(failures) else "FAIL"
    result = M336K11OfficialExecutableBindingReceipt(
        **body, receipt_hash=content_hash(body)
    )
    result.verify()
    if result.status != "PASS":
        raise M336K2ProtocolError("M336K11 official executable binding rejected")
    return result


def build_m336k11_final_request_binding(
    *, official_controller_executable_binding_hash: str, builder_identity_hash: str
) -> dict[str, Any]:
    """Create the path-free request commitment used before and after F36."""

    if not _is_hash(official_controller_executable_binding_hash) or not _is_hash(
        builder_identity_hash
    ):
        raise M336K2ProtocolError("M336K11 final request binding input changed")
    body = {
        "schema_version": 1,
        "contract_role": "M336K11_FINAL_REQUEST_EXECUTABLE_BINDING",
        "official_controller_executable_binding_hash": (
            official_controller_executable_binding_hash
        ),
        "builder_identity_hash": builder_identity_hash,
    }
    return {**body, "request_binding_hash": content_hash(body)}


def build_official_executable_components(**values: Any) -> dict[str, Any]:
    """Build active names only from the canonical official v4 binding inputs."""

    required = {
        "manifest",
        "effective_environment",
        "official_binding",
        "native_capsule",
        "native_route",
    }
    if set(values) != required:
        raise M336K2ProtocolError("M336K11 official executable inputs changed")
    manifest = values["manifest"]
    effective = values["effective_environment"]
    binding = values["official_binding"]
    capsule = values["native_capsule"]
    route = values["native_route"]
    manifest.verify()
    effective.verify()
    binding.verify()
    capsule.verify()
    route.verify()
    if (
        manifest.execution_scope != OFFICIAL_CONTROLLER
        or effective.execution_scope != OFFICIAL_CONTROLLER
        or capsule.execution_scope != OFFICIAL_CONTROLLER
        or binding.execution_scope != OFFICIAL_CONTROLLER
        or route.execution_scope != OFFICIAL_CONTROLLER
    ):
        raise M336K2ProtocolError("M336K11 official executable scope changed")
    manifest_value = manifest.canonical_object()
    return {
        "controller_executable_dependency_manifest": manifest_value,
        "executable_dependency_manifest": manifest_value,
        "effective_environment_binding": effective.canonical_object(),
        "official_controller_executable_binding": binding.canonical_object(),
        "execution_capsule_receipt": capsule.canonical_object(),
        "native_route_manifest": route.canonical_object(),
    }


def build_rehearsal_executable_components(**values: Any) -> dict[str, Any]:
    required = {"manifest", "effective_environment", "native_capsule"}
    if set(values) != required:
        raise M336K2ProtocolError("M336K11 rehearsal executable inputs changed")
    manifest = values["manifest"]
    effective = values["effective_environment"]
    capsule = values["native_capsule"]
    manifest.verify()
    effective.verify()
    capsule.verify()
    if (
        manifest.execution_scope != REHEARSAL
        or effective.execution_scope != REHEARSAL
        or capsule.execution_scope != REHEARSAL
    ):
        raise M336K2ProtocolError("M336K11 rehearsal executable scope changed")
    manifest_value = manifest.canonical_object()
    return {
        "controller_executable_dependency_manifest": manifest_value,
        "executable_dependency_manifest": manifest_value,
        "effective_environment_binding": effective.canonical_object(),
        "execution_capsule_receipt": capsule.canonical_object(),
    }


@dataclass(frozen=True)
class M336K11PostFreezeInputBundle(M336K10PostFreezeInputBundle):
    official_controller_executable_binding_hash: str
    effective_environment_binding_receipt_hash: str
    native_execution_capsule_receipt_hash: str
    native_route_manifest_hash: str
    official_executable_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K11_POST_FREEZE_INPUT_BUNDLE_V4"

    def verify(self) -> None:
        body = self._body()
        if (
            self.schema_version != 4
            or self.contract_role != self.ROLE
            or self.acquisition_policy_hash != self.official_acquisition_policy_hash
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.bundle_hash != content_hash(body)
        ):
            raise M336K2ProtocolError("M336K11 post-freeze bundle is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 4, "contract_role": cls.ROLE, **values}
        if set(body) != {field.name for field in fields(cls)} - {"bundle_hash"}:
            raise M336K2ProtocolError("M336K11 post-freeze bundle inputs changed")
        result = cls(**body, bundle_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "post-freeze bundle"))
        result.verify()
        return result
