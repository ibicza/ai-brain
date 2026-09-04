"""Fail-closed subprocess and network audit for Java pre-freeze evaluation."""

from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash


@dataclass(frozen=True)
class AllowedSubprocessPolicy:
    command_id: str
    executable_path: str
    executable_hash: str
    normalized_argv: tuple[str, ...]
    purpose: str
    maximum_invocations: int
    policy_hash: str


@dataclass(frozen=True)
class ProcessInvocationReceipt:
    command_id: str
    normalized_argv: tuple[str, ...]
    purpose: str
    invocation_index: int
    receipt_hash: str


@dataclass(frozen=True)
class ProcessAuditReport:
    policy_hash: str
    invocation_receipts: tuple[ProcessInvocationReceipt, ...]
    subprocess_invocation_count: int
    unexpected_subprocess_count: int
    socket_attempts: int
    os_system_attempts: int
    source_execution_count: int
    annotation_processor_invocation_count: int
    generated_class_execution_count: int
    report_hash: str


def exact_subprocess_policy(
    command_id: str,
    argv,
    *,
    purpose: str,
    maximum_invocations: int = 1,
) -> AllowedSubprocessPolicy:
    normalized = tuple(str(item) for item in argv)
    executable = Path(normalized[0]).resolve(strict=True)
    body = {
        "command_id": command_id,
        "executable_path": str(executable),
        "executable_hash": bytes_hash(executable.read_bytes()),
        "normalized_argv": (str(executable), *normalized[1:]),
        "purpose": purpose,
        "maximum_invocations": maximum_invocations,
    }
    return AllowedSubprocessPolicy(**body, policy_hash=content_hash(body))


class EnforcedProcessAudit:
    def __init__(self, policies: tuple[AllowedSubprocessPolicy, ...]) -> None:
        self.policies = policies
        self._by_argv = {item.normalized_argv: item for item in policies}
        if len(self._by_argv) != len(policies):
            raise ValueError("duplicate subprocess argv policy")
        self._counts = {item.command_id: 0 for item in policies}
        self._receipts: list[ProcessInvocationReceipt] = []
        self._unexpected = 0
        self._sockets = 0
        self._os_system = 0
        self._depth = 0
        self._originals = {}

    def __enter__(self):
        self._originals = {
            "run": subprocess.run,
            "popen": subprocess.Popen,
            "call": subprocess.call,
            "check_call": subprocess.check_call,
            "check_output": subprocess.check_output,
            "system": os.system,
            "socket": socket.socket,
            "connection": socket.create_connection,
        }
        subprocess.run = self._guard(self._originals["run"])
        subprocess.Popen = self._guard(self._originals["popen"])
        subprocess.call = self._guard(self._originals["call"])
        subprocess.check_call = self._guard(self._originals["check_call"])
        subprocess.check_output = self._guard(self._originals["check_output"])
        os.system = self._blocked_system
        socket.socket = self._blocked_socket
        socket.create_connection = self._blocked_socket
        return self

    def __exit__(self, *_args):
        subprocess.run = self._originals["run"]
        subprocess.Popen = self._originals["popen"]
        subprocess.call = self._originals["call"]
        subprocess.check_call = self._originals["check_call"]
        subprocess.check_output = self._originals["check_output"]
        os.system = self._originals["system"]
        socket.socket = self._originals["socket"]
        socket.create_connection = self._originals["connection"]

    def _guard(self, original):
        def guarded(command, *args, **kwargs):
            if self._depth:
                return original(command, *args, **kwargs)
            policy = self._authorize(command)
            self._depth += 1
            try:
                return original(command, *args, **kwargs)
            finally:
                self._depth -= 1
                self._record(policy)

        return guarded

    def _authorize(self, command):
        if isinstance(command, (str, bytes)):
            self._unexpected += 1
            raise PermissionError("string subprocess commands are forbidden")
        normalized = tuple(str(item) for item in command)
        try:
            executable = str(Path(normalized[0]).resolve(strict=True))
        except (OSError, IndexError) as error:
            self._unexpected += 1
            raise PermissionError("subprocess executable is not exact") from error
        normalized = (executable, *normalized[1:])
        policy = self._by_argv.get(normalized)
        if policy is None:
            self._unexpected += 1
            raise PermissionError("subprocess command is outside the exact allowlist")
        if bytes_hash(Path(executable).read_bytes()) != policy.executable_hash:
            self._unexpected += 1
            raise PermissionError("subprocess executable bytes changed")
        if self._counts[policy.command_id] >= policy.maximum_invocations:
            self._unexpected += 1
            raise PermissionError("subprocess invocation count exceeded policy")
        return policy

    def _record(self, policy):
        self._counts[policy.command_id] += 1
        body = {
            "command_id": policy.command_id,
            "normalized_argv": policy.normalized_argv,
            "purpose": policy.purpose,
            "invocation_index": self._counts[policy.command_id],
        }
        self._receipts.append(
            ProcessInvocationReceipt(**body, receipt_hash=content_hash(body))
        )

    def _blocked_system(self, *_args, **_kwargs):
        self._os_system += 1
        raise PermissionError("os.system is forbidden by process policy")

    def _blocked_socket(self, *_args, **_kwargs):
        self._sockets += 1
        raise PermissionError("network is forbidden by process policy")

    def report(self) -> ProcessAuditReport:
        policy_hash = content_hash(tuple(asdict(item) for item in self.policies))
        source = sum(item.purpose == "JAVA_SOURCE_EXECUTION" for item in self._receipts)
        generated = sum(
            item.purpose == "GENERATED_CLASS_EXECUTION" for item in self._receipts
        )
        annotation = sum(
            item.purpose == "JAVAC_ORACLE" and "-proc:none" not in item.normalized_argv
            for item in self._receipts
        )
        body = {
            "policy_hash": policy_hash,
            "invocation_receipts": tuple(self._receipts),
            "subprocess_invocation_count": len(self._receipts),
            "unexpected_subprocess_count": self._unexpected,
            "socket_attempts": self._sockets,
            "os_system_attempts": self._os_system,
            "source_execution_count": source,
            "annotation_processor_invocation_count": annotation,
            "generated_class_execution_count": generated,
        }
        return ProcessAuditReport(**body, report_hash=content_hash(body))
