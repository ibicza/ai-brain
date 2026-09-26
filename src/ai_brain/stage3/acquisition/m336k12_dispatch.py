"""Canonical native-stage dispatch authority for M-33.6k.12.

The v5 route keeps the outer Python launch and the inner stage target separate.
The historical :class:`M336K2CommandSpec` container is retained only through the
explicit ``m336k12.legacy-command-envelope.v1`` adapter below.  Its leading
``-B`` token is a compatibility marker, not an interpreter argument.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2_COMMAND_EVENTS,
    M336K2CommandSpec,
    M336K2PrivateExecutionPlan,
    build_command_spec,
    build_m336k2_private_execution_plan,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5_REQUIRED_INTERPRETER_ARGUMENTS,
    M336K5PythonInvocationPlan,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k11_execution import (
    OFFICIAL_CONTROLLER,
    M336K11NativeExecutionCapsuleReceipt,
    M336K11NativeRouteManifest,
    M336K11OfficialControllerExecutableBinding,
    M336K11PostFreezeInputBundle,
)

M336K12_PROFILE_ID = "m336k8-final-v5"
M336K12_DISPATCH_ADAPTER_VERSION = "m336k12.legacy-command-envelope.v1"
M336K12_COMPATIBILITY_MARKER = "-B"
M336K12_STAGE_WORKER = "scripts/m336k2_run_stage.py"
M336K12_BOOTSTRAP = "scripts/m336k5_python_bootstrap.py"
M336K12_TARGET_ARGUMENT_FLAGS = ("--request", "--event", "--receipt")
M336K12_EXECUTION_SCOPES = frozenset({"OFFICIAL_CONTROLLER", "REHEARSAL"})
M336K12_MUTATION_CASES = (
    "inner-command-begins-s-and-b",
    "inner-command-begins-only-s",
    "compatibility-marker-missing",
    "duplicate-compatibility-marker",
    "target-and-marker-swapped",
    "target-offset-changed-by-one",
    "target-path-changed",
    "target-source-bytes-changed",
    "request-flag-removed",
    "request-value-offset-changed",
    "event-flag-removed",
    "event-value-changed",
    "receipt-flag-removed",
    "receipt-value-duplicated",
    "two-events-share-receipt-path",
    "event-ordering-changed",
    "event-omitted",
    "extra-event-added",
    "executable-binding-changed",
    "outer-s-omitted",
    "outer-b-omitted",
    "outer-s-duplicated",
    "outer-b-duplicated",
    "bootstrap-bypassed",
    "direct-stage-script-bypassing-bootstrap",
    "producer-source-changed-fully-rehashed",
    "consumer-source-changed-fully-rehashed",
    "dispatch-adapter-version-changed",
    "f36-producer-used-with-v5-consumer",
    "v5-producer-used-with-f36-consumer",
    "f36-native-capsule-used-in-v5",
    "parity-receipt-forged-pass",
    "plan-preflight-omitted-from-validate-only",
    "plan-preflight-omitted-from-controller-admission",
    "first-stage-proof-replaced-by-parser-call",
    "disposable-route-uses-historical-builder",
    "route-event-appended-before-plan-admission",
    "subprocess-started-before-plan-admission",
    "startup-receipt-from-another-plan",
    "target-arguments-include-private-environment-value",
    "historical-v4-profile-used-for-v5-plan",
    "native-capsule-command-hash-kept-stale",
    "published-freeze-plan-validation-path-changed",
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
        raise M336K2ProtocolError(f"M336K12 {label} fields changed")
    return dict(value)


def _repository_path(root: Path, value: str) -> Path:
    relative = Path(*value.split("/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise M336K2ProtocolError("M336K12 target repository path changed")
    target = root.joinpath(relative).resolve(strict=True)
    if not target.is_relative_to(root):
        raise M336K2ProtocolError("M336K12 target escaped repository")
    return target


def _target_argument_template(event: str) -> tuple[str, ...]:
    return (
        "--request",
        "{PRIVATE_STAGE_REQUEST}",
        "--event",
        event,
        "--receipt",
        f"{{PRIVATE_STAGE_RECEIPTS}}/{event}.json",
    )


def verify_m336k12_freeze_plan_admission(
    *,
    plan: M336K5PythonInvocationPlan,
    exact_implementation_tip: str,
    exact_qualification_sha: str,
) -> None:
    """Reject a post-Q freeze plan that cannot be reused after F commits."""

    if not _is_sha(exact_implementation_tip) or not _is_sha(exact_qualification_sha):
        raise M336K2ProtocolError("M336K12 freeze plan lineage is invalid")
    if exact_qualification_sha == exact_implementation_tip:
        return
    validate = plan.validate_arguments
    execute = plan.execute_arguments
    if (
        plan.process_role != "FINAL_CONTROLLER"
        or len(validate) != 5
        or validate[0] != "--request"
        or validate[2] != "--validate-only"
        or validate[3] != "--validation-receipt"
        or len(execute) != 6
        or execute[0] != "--request"
        or execute[2] != "--post-freeze-validation-receipt"
        or execute[4] != "--reservation-release-receipt"
    ):
        raise M336K2ProtocolError(
            "M336K12 published freeze plan operation shape changed"
        )
    request_path = validate[1]
    validation_path = validate[4]
    release_path = execute[5]
    bound_paths = (
        request_path,
        validation_path,
        release_path,
        plan.validate_startup_receipt,
        plan.execute_startup_receipt,
    )
    if (
        execute[1] != request_path
        or execute[3] != validation_path
        or len(set(bound_paths)) != len(bound_paths)
        or any(not Path(value).is_absolute() for value in bound_paths)
        or any("prospective" in Path(value).name.casefold() for value in bound_paths)
    ):
        raise M336K2ProtocolError(
            "M336K12 published freeze plan is not final-controller stable"
        )


@dataclass(frozen=True)
class M336K12NativeStageDispatch:
    schema_version: int
    contract_role: str
    execution_scope: str
    event: str
    outer_interpreter_argument_hash: str
    bootstrap_source_hash: str
    target_repository_path: str
    target_source_hash: str
    target_argument_template: tuple[str, ...]
    target_argument_template_hash: str
    working_directory_identity_hash: str
    receipt_role: str
    expected_status: str
    dispatch_adapter_version: str
    dispatch_hash: str

    ROLE: ClassVar[str] = "M336K12_NATIVE_STAGE_DISPATCH"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("dispatch_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "dispatch_hash": self.dispatch_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K12_EXECUTION_SCOPES
            or self.event not in M336K2_COMMAND_EVENTS
            or self.outer_interpreter_argument_hash
            != content_hash(M336K5_REQUIRED_INTERPRETER_ARGUMENTS)
            or self.target_repository_path != M336K12_STAGE_WORKER
            or self.target_argument_template != _target_argument_template(self.event)
            or self.target_argument_template_hash
            != content_hash(self.target_argument_template)
            or self.receipt_role != "M336K2_NATIVE_STAGE_RECEIPT"
            or self.expected_status != "PASS"
            or self.dispatch_adapter_version != M336K12_DISPATCH_ADAPTER_VERSION
            or any(not _is_hash(item) for item in hashes)
            or self.dispatch_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 native stage dispatch is invalid")

    @classmethod
    def build(
        cls,
        *,
        repository: Path,
        event: str,
        execution_scope: str,
        bootstrap_script: Path,
    ) -> Self:
        root = repository.resolve(strict=True)
        target = _repository_path(root, M336K12_STAGE_WORKER)
        bootstrap = bootstrap_script.resolve(strict=True)
        template = _target_argument_template(event)
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": execution_scope,
            "event": event,
            "outer_interpreter_argument_hash": content_hash(
                M336K5_REQUIRED_INTERPRETER_ARGUMENTS
            ),
            "bootstrap_source_hash": bytes_hash(bootstrap.read_bytes()),
            "target_repository_path": M336K12_STAGE_WORKER,
            "target_source_hash": bytes_hash(target.read_bytes()),
            "target_argument_template": template,
            "target_argument_template_hash": content_hash(template),
            # Public dispatch identities must be independent of the private
            # checkout path.  The active working directory authority is the
            # repository root, represented canonically as ``.``.
            "working_directory_identity_hash": content_hash("."),
            "receipt_role": "M336K2_NATIVE_STAGE_RECEIPT",
            "expected_status": "PASS",
            "dispatch_adapter_version": M336K12_DISPATCH_ADAPTER_VERSION,
        }
        result = cls(**body, dispatch_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        body = _strict(value, cls, "native stage dispatch")
        template = body.get("target_argument_template")
        if type(template) not in {list, tuple}:
            raise M336K2ProtocolError("M336K12 target argument template changed")
        result = cls(**{**body, "target_argument_template": tuple(template)})
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12AdaptedNativeStageCommand:
    """Private parsed command; never publish its absolute values."""

    event: str
    executable: Path
    target: Path
    target_arguments: tuple[str, ...]
    working_directory: Path
    receipt_path: Path
    expected_status: str


def adapt_m336k12_legacy_command(
    command: M336K2CommandSpec,
    dispatch: M336K12NativeStageDispatch,
    *,
    repository: Path,
) -> M336K12AdaptedNativeStageCommand:
    """Parse exactly one frozen v5 compatibility envelope.

    No alternate offsets are accepted.  In particular, ``("-s", "-B", ...)``
    is rejected rather than guessed or retried.
    """

    dispatch.verify()
    root = repository.resolve(strict=True)
    expected_target = _repository_path(root, dispatch.target_repository_path)
    body = asdict(command)
    claimed = body.pop("specification_hash")
    if claimed != content_hash(body):
        raise M336K2ProtocolError("M336K12 command specification hash changed")
    arguments = command.arguments
    if type(arguments) is not tuple or len(arguments) != 8:
        raise M336K2ProtocolError("M336K12 native stage envelope length changed")
    marker, target_value, *target_arguments = arguments
    target_arguments_tuple = tuple(target_arguments)
    if marker != M336K12_COMPATIBILITY_MARKER:
        raise M336K2ProtocolError("M336K12 compatibility marker changed")
    if marker in target_arguments_tuple or "-s" in target_arguments_tuple:
        raise M336K2ProtocolError("M336K12 interpreter flag entered target arguments")
    try:
        target = Path(target_value).resolve(strict=True)
        executable = Path(command.executable).resolve(strict=True)
        working_directory = Path(command.working_directory).resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise M336K2ProtocolError("M336K12 command path is invalid") from error
    receipt_path = Path(command.receipt_path).resolve(strict=False)
    if (
        command.event != dispatch.event
        or target != expected_target
        or bytes_hash(target.read_bytes()) != dispatch.target_source_hash
        or working_directory != root
        or dispatch.working_directory_identity_hash != content_hash(".")
        or target_arguments_tuple[0::2] != M336K12_TARGET_ARGUMENT_FLAGS
        or target_arguments_tuple[3] != command.event
        or Path(target_arguments_tuple[1]).resolve(strict=False).is_dir()
        or Path(target_arguments_tuple[5]).resolve(strict=False) != receipt_path
        or command.receipt_hash_field != "receipt_hash"
        or command.expected_status != dispatch.expected_status
    ):
        raise M336K2ProtocolError("M336K12 native stage command shape changed")
    return M336K12AdaptedNativeStageCommand(
        event=command.event,
        executable=executable,
        target=target,
        target_arguments=target_arguments_tuple,
        working_directory=working_directory,
        receipt_path=receipt_path,
        expected_status=command.expected_status,
    )


def build_m336k12_native_stage_dispatches(
    *,
    repository: Path,
    execution_scope: str,
    bootstrap_script: Path,
) -> tuple[M336K12NativeStageDispatch, ...]:
    dispatches = tuple(
        M336K12NativeStageDispatch.build(
            repository=repository,
            event=event,
            execution_scope=execution_scope,
            bootstrap_script=bootstrap_script,
        )
        for event in M336K2_COMMAND_EVENTS
    )
    if tuple(item.event for item in dispatches) != M336K2_COMMAND_EVENTS:
        raise M336K2ProtocolError("M336K12 dispatch order changed")
    return dispatches


def build_m336k12_native_execution_plan(
    *,
    repository: Path,
    python_executable: Path,
    stage_request: Path,
    stage_receipt_root: Path,
    route_run_id: str,
    exact_f37_sha: str,
    route_registry_hash: str,
    dispatches: tuple[M336K12NativeStageDispatch, ...],
) -> M336K2PrivateExecutionPlan:
    """Adapt typed v5 dispatches into the frozen historical private container."""

    root = repository.resolve(strict=True)
    python = python_executable.resolve(strict=True)
    request = stage_request.resolve(strict=False)
    receipts = stage_receipt_root.resolve(strict=False)
    if not _is_sha(exact_f37_sha) or not _is_hash(route_registry_hash):
        raise M336K2ProtocolError("M336K12 native plan identity changed")
    if tuple(item.event for item in dispatches) != M336K2_COMMAND_EVENTS:
        raise M336K2ProtocolError("M336K12 native plan dispatch order changed")
    commands = []
    for dispatch in dispatches:
        dispatch.verify()
        target = _repository_path(root, dispatch.target_repository_path)
        receipt = receipts / f"{dispatch.event}.json"
        commands.append(
            build_command_spec(
                event=dispatch.event,
                executable=python,
                arguments=(
                    M336K12_COMPATIBILITY_MARKER,
                    str(target),
                    "--request",
                    str(request),
                    "--event",
                    dispatch.event,
                    "--receipt",
                    str(receipt),
                ),
                working_directory=root,
                receipt_path=receipt,
                receipt_hash_field="receipt_hash",
                expected_status=dispatch.expected_status,
            )
        )
    return build_m336k2_private_execution_plan(
        route_run_id=route_run_id,
        exact_f28_sha=exact_f37_sha,
        route_registry_hash=route_registry_hash,
        commands=tuple(commands),
    )


@dataclass(frozen=True)
class M336K12PreledgerDispatchAdmissionPolicy:
    """Frozen ordering and active-path requirements checked before route writes."""

    schema_version: int
    contract_role: str
    validate_only_complete_plan_preflight_required: bool
    controller_complete_plan_preflight_required: bool
    first_stage_handoff_mode: str
    official_plan_builder_source_hash: str
    rehearsal_plan_builder_source_hash: str
    official_consumer_source_hash: str
    rehearsal_consumer_source_hash: str
    route_event_count_before_plan_admission: int
    subprocess_start_count_before_plan_admission: int
    status: str
    policy_hash: str

    ROLE: ClassVar[str] = "M336K12_PRELEDGER_DISPATCH_ADMISSION_POLICY"
    FIRST_STAGE_MODE: ClassVar[str] = "EXACT_POWERSHELL_BOOTSTRAP_SUBPROCESS"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("policy_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "policy_hash": self.policy_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.validate_only_complete_plan_preflight_required is not True
            or self.controller_complete_plan_preflight_required is not True
            or self.first_stage_handoff_mode != self.FIRST_STAGE_MODE
            or self.official_plan_builder_source_hash
            != self.rehearsal_plan_builder_source_hash
            or self.official_consumer_source_hash != self.rehearsal_consumer_source_hash
            or self.route_event_count_before_plan_admission != 0
            or self.subprocess_start_count_before_plan_admission != 0
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.status != "PASS"
            or self.policy_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError(
                "M336K12 preledger dispatch admission policy is invalid"
            )

    @classmethod
    def build(cls, repository: Path) -> Self:
        root = repository.resolve(strict=True)
        builder_hash = bytes_hash(Path(__file__).resolve(strict=True).read_bytes())
        consumer_hash = bytes_hash(
            (root / "src/ai_brain/stage3/acquisition/m336k5_execution.py").read_bytes()
        )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "validate_only_complete_plan_preflight_required": True,
            "controller_complete_plan_preflight_required": True,
            "first_stage_handoff_mode": cls.FIRST_STAGE_MODE,
            "official_plan_builder_source_hash": builder_hash,
            "rehearsal_plan_builder_source_hash": builder_hash,
            "official_consumer_source_hash": consumer_hash,
            "rehearsal_consumer_source_hash": consumer_hash,
            "route_event_count_before_plan_admission": 0,
            "subprocess_start_count_before_plan_admission": 0,
            "status": "PASS",
        }
        result = cls(**body, policy_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "preledger dispatch admission policy"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12NativeStagePlanBinding:
    schema_version: int
    contract_role: str
    exact_implementation_tip: str
    active_profile_hash: str
    route_registry_hash: str
    typed_route_manifest_hash: str
    event_sequence: tuple[str, ...]
    event_sequence_hash: str
    dispatch_count: int
    dispatch_hashes: tuple[str, ...]
    python_executable_bytes_hash: str
    plan_builder_source_hash: str
    consumer_source_hash: str
    legacy_adapter_source_hash: str
    outer_startup_policy_hash: str
    bootstrap_repository_path: str
    powershell_launcher_source_hash: str
    bootstrap_source_hash: str
    stage_worker_source_hash: str
    native_capsule_receipt_hash: str
    preledger_admission_policy_hash: str
    plan_binding_hash: str

    ROLE: ClassVar[str] = "M336K12_NATIVE_STAGE_PLAN_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("plan_binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "plan_binding_hash": self.plan_binding_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not _is_sha(self.exact_implementation_tip)
            or self.event_sequence != M336K2_COMMAND_EVENTS
            or self.event_sequence_hash != content_hash(self.event_sequence)
            or self.dispatch_count != len(M336K2_COMMAND_EVENTS)
            or len(self.dispatch_hashes) != self.dispatch_count
            or len(set(self.dispatch_hashes)) != self.dispatch_count
            or any(not _is_hash(item) for item in self.dispatch_hashes)
            or any(not _is_hash(item) for item in hashes)
            or self.bootstrap_repository_path != M336K12_BOOTSTRAP
            or self.plan_binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 native stage plan binding is invalid")

    @classmethod
    def build(
        cls,
        *,
        repository: Path,
        exact_implementation_tip: str,
        active_profile_hash: str,
        route_registry_hash: str,
        typed_route_manifest_hash: str,
        dispatches: tuple[M336K12NativeStageDispatch, ...],
        python_executable: Path,
        outer_startup_policy_hash: str,
        native_capsule_receipt_hash: str,
    ) -> Self:
        root = repository.resolve(strict=True)
        python = python_executable.resolve(strict=True)
        paths = {
            "plan_builder_source_hash": Path(__file__).resolve(strict=True),
            "consumer_source_hash": root
            / "src/ai_brain/stage3/acquisition/m336k5_execution.py",
            "legacy_adapter_source_hash": Path(__file__).resolve(strict=True),
            "powershell_launcher_source_hash": root
            / "scripts/m336k5_launch_python.ps1",
            "bootstrap_source_hash": root / "scripts/m336k5_python_bootstrap.py",
            "stage_worker_source_hash": root / M336K12_STAGE_WORKER,
        }
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "exact_implementation_tip": exact_implementation_tip,
            "active_profile_hash": active_profile_hash,
            "route_registry_hash": route_registry_hash,
            "typed_route_manifest_hash": typed_route_manifest_hash,
            "event_sequence": M336K2_COMMAND_EVENTS,
            "event_sequence_hash": content_hash(M336K2_COMMAND_EVENTS),
            "dispatch_count": len(dispatches),
            "dispatch_hashes": tuple(item.dispatch_hash for item in dispatches),
            "python_executable_bytes_hash": bytes_hash(python.read_bytes()),
            **{name: bytes_hash(path.read_bytes()) for name, path in paths.items()},
            "outer_startup_policy_hash": outer_startup_policy_hash,
            "bootstrap_repository_path": M336K12_BOOTSTRAP,
            "native_capsule_receipt_hash": native_capsule_receipt_hash,
            "preledger_admission_policy_hash": (
                M336K12PreledgerDispatchAdmissionPolicy.build(root).policy_hash
            ),
        }
        result = cls(**body, plan_binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        body = _strict(value, cls, "native stage plan binding")
        for name in ("event_sequence", "dispatch_hashes"):
            if type(body.get(name)) not in {list, tuple}:
                raise M336K2ProtocolError(f"M336K12 {name} changed")
            body[name] = tuple(body[name])
        result = cls(**body)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12ProducerConsumerParityReceipt:
    schema_version: int
    contract_role: str
    native_stage_plan_binding_hash: str
    private_execution_plan_hash: str
    dispatch_contract_hash: str
    produced_dispatch_count: int
    accepted_dispatch_count: int
    expected_dispatch_count: int
    target_mismatch_count: int
    target_argument_mismatch_count: int
    outer_inner_flag_ownership_mismatch_count: int
    event_order_mismatch_count: int
    duplicate_receipt_destination_count: int
    producer_authority_count: int
    consumer_authority_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K12_PRODUCER_CONSUMER_PARITY_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        counters = (
            self.target_mismatch_count,
            self.target_argument_mismatch_count,
            self.outer_inner_flag_ownership_mismatch_count,
            self.event_order_mismatch_count,
            self.duplicate_receipt_destination_count,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.expected_dispatch_count != len(M336K2_COMMAND_EVENTS)
            or self.produced_dispatch_count != self.expected_dispatch_count
            or self.accepted_dispatch_count != self.expected_dispatch_count
            or any(counters)
            or self.producer_authority_count != 1
            or self.consumer_authority_count != 1
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 producer/consumer parity failed")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "producer/consumer parity receipt"))
        result.verify()
        return result


def verify_m336k12_native_stage_plan(
    *,
    plan: M336K2PrivateExecutionPlan,
    dispatches: tuple[M336K12NativeStageDispatch, ...],
    plan_binding: M336K12NativeStagePlanBinding,
    repository: Path,
    python_executable: Path | None = None,
) -> M336K12ProducerConsumerParityReceipt:
    """Verify every command without writing files or starting a subprocess."""

    plan_binding.verify()
    root = repository.resolve(strict=True)
    if python_executable is None:
        if not plan.commands:
            raise M336K2ProtocolError("M336K12 native stage plan is empty")
        python_executable = Path(plan.commands[0].executable)
    python = python_executable.resolve(strict=True)
    if not dispatches:
        raise M336K2ProtocolError("M336K12 dispatch set is empty")
    expected_dispatches = build_m336k12_native_stage_dispatches(
        repository=root,
        execution_scope=dispatches[0].execution_scope,
        bootstrap_script=root / "scripts/m336k5_python_bootstrap.py",
    )
    if dispatches != expected_dispatches:
        raise M336K2ProtocolError("M336K12 live dispatch authority changed")
    expected_binding = M336K12NativeStagePlanBinding.build(
        repository=root,
        exact_implementation_tip=plan_binding.exact_implementation_tip,
        active_profile_hash=plan_binding.active_profile_hash,
        route_registry_hash=plan_binding.route_registry_hash,
        typed_route_manifest_hash=plan_binding.typed_route_manifest_hash,
        dispatches=dispatches,
        python_executable=python,
        outer_startup_policy_hash=plan_binding.outer_startup_policy_hash,
        native_capsule_receipt_hash=plan_binding.native_capsule_receipt_hash,
    )
    if plan_binding != expected_binding:
        raise M336K2ProtocolError("M336K12 live plan binding changed")
    if (
        len(
            {Path(command.executable).resolve(strict=True) for command in plan.commands}
        )
        != 1
        or any(
            Path(command.executable).resolve(strict=True) != python
            for command in plan.commands
        )
        or bytes_hash(python.read_bytes()) != plan_binding.python_executable_bytes_hash
        or len(
            {
                command.arguments[3]
                for command in plan.commands
                if len(command.arguments) == 8
            }
        )
        != 1
    ):
        raise M336K2ProtocolError("M336K12 private plan authority changed")
    produced = len(plan.commands)
    accepted = 0
    target_mismatches = 0
    target_argument_mismatches = 0
    flag_mismatches = 0
    order_mismatches = int(
        tuple(command.event for command in plan.commands) != M336K2_COMMAND_EVENTS
        or tuple(dispatch.event for dispatch in dispatches) != M336K2_COMMAND_EVENTS
    )
    receipts: list[Path] = []
    if len(dispatches) == len(plan.commands):
        for command, dispatch in zip(plan.commands, dispatches, strict=True):
            try:
                adapted = adapt_m336k12_legacy_command(
                    command, dispatch, repository=root
                )
            except M336K2ProtocolError:
                target_mismatches += 1
                target_argument_mismatches += 1
                continue
            expected_target = _repository_path(root, dispatch.target_repository_path)
            expected_arguments = (
                "--request",
                command.arguments[3],
                "--event",
                command.event,
                "--receipt",
                command.receipt_path,
            )
            target_mismatches += int(adapted.target != expected_target)
            target_argument_mismatches += int(
                adapted.target_arguments != expected_arguments
            )
            flag_mismatches += sum(
                token in M336K5_REQUIRED_INTERPRETER_ARGUMENTS
                for token in adapted.target_arguments
            )
            receipts.append(adapted.receipt_path)
            accepted += 1
    dispatch_contract_hash = m336k12_native_dispatch_contract_hash(dispatches)
    normalized_private_plan_hash = content_hash(
        (
            "m336k12.private-plan-shape.v1",
            plan.route_registry_hash,
            tuple(dispatch.dispatch_hash for dispatch in dispatches),
        )
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K12ProducerConsumerParityReceipt.ROLE,
        "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
        "private_execution_plan_hash": normalized_private_plan_hash,
        "dispatch_contract_hash": dispatch_contract_hash,
        "produced_dispatch_count": produced,
        "accepted_dispatch_count": accepted,
        "expected_dispatch_count": len(M336K2_COMMAND_EVENTS),
        "target_mismatch_count": target_mismatches,
        "target_argument_mismatch_count": target_argument_mismatches,
        "outer_inner_flag_ownership_mismatch_count": flag_mismatches,
        "event_order_mismatch_count": order_mismatches,
        "duplicate_receipt_destination_count": len(receipts) - len(set(receipts)),
        "producer_authority_count": 1,
        "consumer_authority_count": 1,
    }
    failures = tuple(
        value
        for name, value in body.items()
        if name.endswith("_count")
        and name
        not in {
            "produced_dispatch_count",
            "accepted_dispatch_count",
            "expected_dispatch_count",
            "producer_authority_count",
            "consumer_authority_count",
        }
    )
    body["status"] = (
        "PASS"
        if produced == accepted == len(M336K2_COMMAND_EVENTS) and not any(failures)
        else "FAIL"
    )
    result = M336K12ProducerConsumerParityReceipt(
        **body, receipt_hash=content_hash(body)
    )
    result.verify()
    return result


def m336k12_native_dispatch_contract_hash(
    dispatches: tuple[M336K12NativeStageDispatch, ...],
) -> str:
    for dispatch in dispatches:
        dispatch.verify()
    if tuple(item.event for item in dispatches) != M336K2_COMMAND_EVENTS:
        raise M336K2ProtocolError("M336K12 dispatch contract order changed")
    return content_hash(
        (
            "m336k12.native-stage-dispatch-contract.v1",
            M336K12_DISPATCH_ADAPTER_VERSION,
            M336K12_COMPATIBILITY_MARKER,
            tuple(item.dispatch_hash for item in dispatches),
            "outer-interpreter-arguments-owned-by-startup-policy",
            "inner-interpreter-argument-count=0",
        )
    )


@dataclass(frozen=True)
class M336K12DisposableDispatchClosure:
    """Private rehearsal authority for the active v5 dispatch implementation."""

    schema_version: int
    contract_role: str
    rehearsal_profile_id: str
    rehearsal_profile_hash: str
    rehearsal_profile_status: str
    dispatches: tuple[M336K12NativeStageDispatch, ...]
    native_stage_plan_binding: M336K12NativeStagePlanBinding
    producer_consumer_parity: M336K12ProducerConsumerParityReceipt
    dispatch_contract_hash: str
    official_plan_builder_source_hash: str
    rehearsal_plan_builder_source_hash: str
    official_consumer_source_hash: str
    rehearsal_consumer_source_hash: str
    plan_builder_source_difference_count: int
    consumer_source_difference_count: int
    status: str
    closure_hash: str

    ROLE: ClassVar[str] = "M336K12_DISPOSABLE_DISPATCH_CLOSURE"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "rehearsal_profile_id": self.rehearsal_profile_id,
            "rehearsal_profile_hash": self.rehearsal_profile_hash,
            "rehearsal_profile_status": self.rehearsal_profile_status,
            "dispatches": tuple(item.canonical_object() for item in self.dispatches),
            "native_stage_plan_binding": (
                self.native_stage_plan_binding.canonical_object()
            ),
            "producer_consumer_parity": (
                self.producer_consumer_parity.canonical_object()
            ),
            "dispatch_contract_hash": self.dispatch_contract_hash,
            "official_plan_builder_source_hash": (
                self.official_plan_builder_source_hash
            ),
            "rehearsal_plan_builder_source_hash": (
                self.rehearsal_plan_builder_source_hash
            ),
            "official_consumer_source_hash": self.official_consumer_source_hash,
            "rehearsal_consumer_source_hash": self.rehearsal_consumer_source_hash,
            "plan_builder_source_difference_count": (
                self.plan_builder_source_difference_count
            ),
            "consumer_source_difference_count": self.consumer_source_difference_count,
            "status": self.status,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "closure_hash": self.closure_hash}

    def verify(self) -> None:
        registry = m336k_official_profile_registry()
        profile = registry.profile(self.rehearsal_profile_id)
        for dispatch in self.dispatches:
            dispatch.verify()
        self.native_stage_plan_binding.verify()
        self.producer_consumer_parity.verify()
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
            or self.rehearsal_profile_hash != profile.profile_hash
            or self.rehearsal_profile_status != profile.profile_status.value
            or {item.execution_scope for item in self.dispatches} != {"REHEARSAL"}
            or self.native_stage_plan_binding.active_profile_hash
            != profile.profile_hash
            or self.producer_consumer_parity.native_stage_plan_binding_hash
            != self.native_stage_plan_binding.plan_binding_hash
            or self.dispatch_contract_hash
            != m336k12_native_dispatch_contract_hash(self.dispatches)
            or self.producer_consumer_parity.dispatch_contract_hash
            != self.dispatch_contract_hash
            or self.official_plan_builder_source_hash
            != self.rehearsal_plan_builder_source_hash
            or self.official_plan_builder_source_hash
            != self.native_stage_plan_binding.plan_builder_source_hash
            or self.official_consumer_source_hash != self.rehearsal_consumer_source_hash
            or self.official_consumer_source_hash
            != self.native_stage_plan_binding.consumer_source_hash
            or self.plan_builder_source_difference_count != 0
            or self.consumer_source_difference_count != 0
            or self.status != "PASS"
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.closure_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 disposable dispatch closure is invalid")

    @classmethod
    def build(
        cls,
        *,
        rehearsal_profile_id: str,
        dispatches: tuple[M336K12NativeStageDispatch, ...],
        plan_binding: M336K12NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
    ) -> Self:
        profile = m336k_official_profile_registry().profile(rehearsal_profile_id)
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "rehearsal_profile_id": profile.profile_id,
            "rehearsal_profile_hash": profile.profile_hash,
            "rehearsal_profile_status": profile.profile_status.value,
            "dispatches": dispatches,
            "native_stage_plan_binding": plan_binding,
            "producer_consumer_parity": parity,
            "dispatch_contract_hash": m336k12_native_dispatch_contract_hash(dispatches),
            "official_plan_builder_source_hash": plan_binding.plan_builder_source_hash,
            "rehearsal_plan_builder_source_hash": plan_binding.plan_builder_source_hash,
            "official_consumer_source_hash": plan_binding.consumer_source_hash,
            "rehearsal_consumer_source_hash": plan_binding.consumer_source_hash,
            "plan_builder_source_difference_count": 0,
            "consumer_source_difference_count": 0,
            "status": "PASS",
        }
        temporary = cls(**body, closure_hash="0" * 64)
        result = cls(**body, closure_hash=content_hash(temporary._body()))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        body = _strict(value, cls, "disposable dispatch closure")
        raw_dispatches = body.get("dispatches")
        if type(raw_dispatches) not in {list, tuple}:
            raise M336K2ProtocolError("M336K12 disposable dispatches changed")
        result = cls(
            **{
                **body,
                "dispatches": tuple(
                    M336K12NativeStageDispatch.from_dict(item)
                    for item in raw_dispatches
                ),
                "native_stage_plan_binding": M336K12NativeStagePlanBinding.from_dict(
                    body["native_stage_plan_binding"]
                ),
                "producer_consumer_parity": (
                    M336K12ProducerConsumerParityReceipt.from_dict(
                        body["producer_consumer_parity"]
                    )
                ),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12NativeExecutionCapsuleReceipt(M336K11NativeExecutionCapsuleReceipt):
    native_stage_plan_binding_hash: str
    producer_consumer_parity_receipt_hash: str
    dispatch_contract_hash: str
    historical_base_capsule_receipt_hash: str

    ROLE: ClassVar[str] = "M336K12_NATIVE_EXECUTION_CAPSULE_RECEIPT_V3"

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 3
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K12_EXECUTION_SCOPES
            or not _is_sha(self.exact_implementation_tip)
            or self.stage_worker_repository_path != M336K12_STAGE_WORKER
            or self.command_contract_hash != self.dispatch_contract_hash
            or any(not _is_hash(item) for item in hashes)
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 native execution capsule is invalid")

    @classmethod
    def build(
        cls,
        *,
        base_capsule: M336K11NativeExecutionCapsuleReceipt,
        plan_binding: M336K12NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
        dispatches: tuple[M336K12NativeStageDispatch, ...],
    ) -> Self:
        base_capsule.verify()
        plan_binding.verify()
        parity.verify()
        if {item.execution_scope for item in dispatches} != {
            base_capsule.execution_scope
        }:
            raise M336K2ProtocolError("M336K12 native capsule dispatch scope changed")
        contract_hash = m336k12_native_dispatch_contract_hash(dispatches)
        body = {
            **{
                field.name: getattr(base_capsule, field.name)
                for field in fields(type(base_capsule))
                if field.name not in {"schema_version", "contract_role", "receipt_hash"}
            },
            "schema_version": 3,
            "contract_role": cls.ROLE,
            "command_contract_hash": contract_hash,
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "producer_consumer_parity_receipt_hash": parity.receipt_hash,
            "dispatch_contract_hash": contract_hash,
            "historical_base_capsule_receipt_hash": base_capsule.receipt_hash,
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "native execution capsule"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12OfficialControllerExecutableBinding(
    M336K11OfficialControllerExecutableBinding
):
    native_stage_plan_binding_hash: str
    producer_consumer_parity_receipt_hash: str
    native_execution_capsule_receipt_hash: str
    dispatch_contract_hash: str

    ROLE: ClassVar[str] = "M336K12_OFFICIAL_CONTROLLER_EXECUTABLE_BINDING"

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.execution_scope != OFFICIAL_CONTROLLER
            or self.official_profile_id != M336K12_PROFILE_ID
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
            or self.official_profile_hash != profile.profile_hash
            or not _is_sha(self.exact_implementation_tip)
            or self.native_command_contract_hash != self.dispatch_contract_hash
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 official executable binding is invalid")

    @classmethod
    def build(
        cls,
        *,
        base_binding: M336K11OfficialControllerExecutableBinding,
        profile: M336KOfficialRouteProfile,
        capsule: M336K12NativeExecutionCapsuleReceipt,
        plan_binding: M336K12NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
    ) -> Self:
        profile.verify()
        capsule.verify()
        plan_binding.verify()
        parity.verify()
        body = {
            **{
                field.name: getattr(base_binding, field.name)
                for field in fields(type(base_binding))
                if field.name
                not in {
                    "schema_version",
                    "contract_role",
                    "official_profile_id",
                    "official_profile_hash",
                    "native_command_contract_hash",
                    "binding_hash",
                }
            },
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "official_profile_id": profile.profile_id,
            "official_profile_hash": profile.profile_hash,
            "native_command_contract_hash": capsule.dispatch_contract_hash,
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "producer_consumer_parity_receipt_hash": parity.receipt_hash,
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "dispatch_contract_hash": capsule.dispatch_contract_hash,
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
class M336K12NativeRouteManifest(M336K11NativeRouteManifest):
    native_stage_plan_binding_hash: str
    producer_consumer_parity_receipt_hash: str
    dispatch_contract_hash: str

    ROLE: ClassVar[str] = "M336K12_ACTIVE_NATIVE_ROUTE_MANIFEST"

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.execution_scope != OFFICIAL_CONTROLLER
            or self.official_profile_id != M336K12_PROFILE_ID
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
            raise M336K2ProtocolError("M336K12 active native route is invalid")

    @classmethod
    def build(
        cls,
        *,
        profile: M336KOfficialRouteProfile,
        binding: M336K12OfficialControllerExecutableBinding,
        capsule: M336K12NativeExecutionCapsuleReceipt,
        plan_binding: M336K12NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
    ) -> Self:
        profile.verify()
        binding.verify()
        capsule.verify()
        plan_binding.verify()
        parity.verify()
        body = {
            "schema_version": 2,
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
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "producer_consumer_parity_receipt_hash": parity.receipt_hash,
            "dispatch_contract_hash": capsule.dispatch_contract_hash,
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
class M336K12OfficialExecutableBindingReceipt:
    schema_version: int
    contract_role: str
    executable_semantic_anchor_hash: str
    official_controller_executable_binding_hash: str
    native_execution_capsule_receipt_hash: str
    native_route_manifest_hash: str
    native_stage_plan_binding_hash: str
    producer_consumer_parity_receipt_hash: str
    dispatch_contract_hash: str
    executable_semantic_mismatch_count: int
    dispatch_semantic_mismatch_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K12_OFFICIAL_EXECUTABLE_BINDING_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.executable_semantic_mismatch_count != 0
            or self.dispatch_semantic_mismatch_count != 0
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 executable binding receipt is invalid")

    @classmethod
    def build(
        cls,
        *,
        executable_semantic_anchor_hash: str,
        executable_semantic_mismatch_count: int,
        binding: M336K12OfficialControllerExecutableBinding,
        capsule: M336K12NativeExecutionCapsuleReceipt,
        route: M336K12NativeRouteManifest,
        plan_binding: M336K12NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
    ) -> Self:
        binding.verify()
        capsule.verify()
        route.verify()
        plan_binding.verify()
        parity.verify()
        if not _is_hash(executable_semantic_anchor_hash):
            raise M336K2ProtocolError("M336K12 executable semantic anchor is invalid")
        mismatches = sum(
            (
                binding.native_stage_plan_binding_hash
                != plan_binding.plan_binding_hash,
                capsule.native_stage_plan_binding_hash
                != plan_binding.plan_binding_hash,
                route.native_stage_plan_binding_hash != plan_binding.plan_binding_hash,
                binding.producer_consumer_parity_receipt_hash != parity.receipt_hash,
                capsule.producer_consumer_parity_receipt_hash != parity.receipt_hash,
                route.producer_consumer_parity_receipt_hash != parity.receipt_hash,
                binding.dispatch_contract_hash != capsule.dispatch_contract_hash,
                route.dispatch_contract_hash != capsule.dispatch_contract_hash,
            )
        )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "executable_semantic_anchor_hash": executable_semantic_anchor_hash,
            "official_controller_executable_binding_hash": binding.binding_hash,
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "native_route_manifest_hash": route.manifest_hash,
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "producer_consumer_parity_receipt_hash": parity.receipt_hash,
            "dispatch_contract_hash": capsule.dispatch_contract_hash,
            "executable_semantic_mismatch_count": executable_semantic_mismatch_count,
            "dispatch_semantic_mismatch_count": mismatches,
            "status": (
                "PASS"
                if mismatches == 0 and executable_semantic_mismatch_count == 0
                else "FAIL"
            ),
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "executable binding receipt"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12PostFreezeInputBundle(M336K11PostFreezeInputBundle):
    native_stage_plan_binding_hash: str
    producer_consumer_parity_receipt_hash: str
    dispatch_contract_hash: str

    ROLE: ClassVar[str] = "M336K12_POST_FREEZE_INPUT_BUNDLE_V5"

    def verify(self) -> None:
        if (
            self.schema_version != 5
            or self.contract_role != self.ROLE
            or self.acquisition_policy_hash != self.official_acquisition_policy_hash
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.bundle_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K12 post-freeze bundle is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 5, "contract_role": cls.ROLE, **values}
        if set(body) != {field.name for field in fields(cls)} - {"bundle_hash"}:
            raise M336K2ProtocolError("M336K12 post-freeze bundle inputs changed")
        result = cls(**body, bundle_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "post-freeze bundle"))
        result.verify()
        return result
