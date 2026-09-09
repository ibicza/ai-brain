"""Oracle-free javac diagnostics and declaration bindings for production trust."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_diagnostic_scope import JavaDiagnosticScope
from ai_brain.stage3.acquisition.java_jdk_provider import (
    frozen_m336_jdk_provider_manifest,
)
from ai_brain.stage3.acquisition.java_source_index import (
    JavaSourceIndex,
    declaration_by_node_id,
)
from ai_brain.stage3.acquisition.models import SourceBundle

M336F_COMPILER_POLICY_VERSION = "m336f.production-javac-diagnostics.v2"
M336F_DIAGNOSTIC_BINDING_VERSION = "m336f.declaration-diagnostic-binding.v1"
_DIAGNOSTIC = re.compile(
    r"^(?P<path>.+\.java):(?P<line>[0-9]+):(?P<column>[0-9]+): "
    r"(?P<code>[a-z][a-z0-9_.-]*)(?::(?P<payload>.*))?$"
)
_SUMMARY = re.compile(r"^[0-9]+ (?:error|errors|warning|warnings)$")
_NOTE = re.compile(r"^- compiler\.note\.[a-z0-9_.-]+(?::.*)?$")
_TYPE_KINDS = frozenset({"class", "interface", "enum", "record", "annotation"})
_CALLABLE_KINDS = frozenset({"method", "constructor"})
_AMBIENT_BLOCKING_CATEGORIES = frozenset(
    {"DUPLICATE_SIGNATURE", "INVALID_IMPORT", "COMPILER_ENVIRONMENT_MISMATCH"}
)


@dataclass(frozen=True)
class JavaProductionCompilationProbe:
    schema_version: int
    policy_version: str
    provider_manifest_hash: str
    compiler_identity_hash: str
    javac_sha256: str
    javac_version: str
    release: int
    encoding: str
    annotation_processing: bool
    locale_policy: str
    classpath_manifest_hash: str
    probe_hash: str


@dataclass(frozen=True)
class JavaCompilerDiagnostic:
    source_entry_id: str | None
    source_unit_id: str | None
    source_unit_identity: str | None
    diagnostic_code: str
    normalized_category: str
    diagnostic_kind: str
    line: int | None
    column: int | None
    canonical_position: int | None
    canonical_byte_start: int | None
    canonical_byte_end: int | None
    diagnostic_hash: str


@dataclass(frozen=True)
class DeclarationDiagnosticBinding:
    compilation_run_hash: str
    diagnostic_hash: str
    source_entry_id: str | None
    source_unit_id: str | None
    source_unit_identity: str | None
    compiler_diagnostic_code: str
    normalized_category: str
    canonical_position: int | None
    canonical_byte_start: int | None
    canonical_byte_end: int | None
    declaration_ids: tuple[str, ...]
    diagnostic_scope: JavaDiagnosticScope
    enclosing_type_identity: str | None
    binding_hash: str


@dataclass(frozen=True)
class JavaProductionCompilerReport:
    schema_version: int
    compiler_policy_version: str
    compiler_identity_hash: str
    compilation_run_hash: str
    source_manifest_hash: str
    source_file_count: int
    diagnostic_count: int
    error_count: int
    warning_count: int
    unknown_scope_count: int
    unmapped_diagnostic_count: int
    source_unit_unbound_count: int
    malformed_output_count: int
    malformed_output_hashes: tuple[str, ...]
    process_exit_code: int
    diagnostics: tuple[JavaCompilerDiagnostic, ...]
    bindings: tuple[DeclarationDiagnosticBinding, ...]
    report_hash: str


@dataclass(frozen=True)
class JavaCompilationTrustGate:
    schema_version: int
    compiler_report_hash: str
    compilation_policy_hash: str
    blocked_declaration_ids: tuple[str, ...]
    applicable_blocking_diagnostic_hashes: tuple[tuple[str, tuple[str, ...]], ...]
    batch_blocked: bool
    blocked_declaration_count: int
    gate_hash: str


def java_production_compiler_identity_hash(
    *,
    provider_manifest_hash: str,
    javac_version: str,
    release: int,
    classpath_manifest_hash: str,
) -> str:
    """Identify cross-platform compiler semantics, not a host executable."""

    return content_hash(
        {
            "policy_version": M336F_COMPILER_POLICY_VERSION,
            "provider_manifest_hash": provider_manifest_hash,
            "javac_version": javac_version,
            "release": release,
            "encoding": "UTF-8",
            "annotation_processing": False,
            "locale_policy": "JAVAC_XDRAWDIAGNOSTICS_EN_US",
            "classpath_manifest_hash": classpath_manifest_hash,
        }
    )


def build_java_production_compilation_probe(
    javac_executable: Path,
    *,
    release: int = 21,
    classpath_identities: tuple[str, ...] = (),
) -> JavaProductionCompilationProbe:
    javac = javac_executable.resolve(strict=True)
    provider = frozen_m336_jdk_provider_manifest()
    javac_sha256 = bytes_hash(javac.read_bytes())
    platform_identity = next(
        (item for item in provider.platforms if item.javac_sha256 == javac_sha256),
        None,
    )
    if platform_identity is None:
        raise ValueError("production javac is not in the frozen JDK provider manifest")
    version = f"javac {platform_identity.version}"
    identity = {
        "policy_version": M336F_COMPILER_POLICY_VERSION,
        "provider_manifest_hash": provider.manifest_hash,
        "javac_version": version,
        "release": release,
        "encoding": "UTF-8",
        "annotation_processing": False,
        "locale_policy": "JAVAC_XDRAWDIAGNOSTICS_EN_US",
        "classpath_manifest_hash": content_hash(tuple(sorted(classpath_identities))),
    }
    body = {
        "schema_version": 2,
        **identity,
        "compiler_identity_hash": java_production_compiler_identity_hash(
            provider_manifest_hash=provider.manifest_hash,
            javac_version=version,
            release=release,
            classpath_manifest_hash=identity["classpath_manifest_hash"],
        ),
        "javac_sha256": javac_sha256,
    }
    return JavaProductionCompilationProbe(**body, probe_hash=content_hash(body))


def verify_java_production_compilation_probe(
    probe: JavaProductionCompilationProbe, javac_executable: Path
) -> None:
    verify_java_production_compilation_probe_receipt(probe)
    javac = javac_executable.resolve(strict=True)
    if bytes_hash(javac.read_bytes()) != probe.javac_sha256:
        raise ValueError("production compiler executable changed after probe")


def verify_java_production_compilation_probe_receipt(
    probe: JavaProductionCompilationProbe,
) -> None:
    """Verify a copied probe receipt without requiring its platform executable."""

    body = asdict(probe)
    claimed = body.pop("probe_hash")
    provider = frozen_m336_jdk_provider_manifest()
    platform_identity = next(
        (
            item
            for item in provider.platforms
            if item.javac_sha256 == probe.javac_sha256
        ),
        None,
    )
    if (
        content_hash(body) != claimed
        or probe.schema_version != 2
        or probe.policy_version != M336F_COMPILER_POLICY_VERSION
        or probe.provider_manifest_hash != provider.manifest_hash
        or probe.compiler_identity_hash
        != java_production_compiler_identity_hash(
            provider_manifest_hash=probe.provider_manifest_hash,
            javac_version=probe.javac_version,
            release=probe.release,
            classpath_manifest_hash=probe.classpath_manifest_hash,
        )
        or probe.release != 21
        or probe.encoding != "UTF-8"
        or probe.annotation_processing
        or platform_identity is None
        or probe.javac_version != f"javac {platform_identity.version}"
    ):
        raise ValueError("production compiler identity or policy changed")


def java_production_compilation_probe_from_dict(
    value: dict,
) -> JavaProductionCompilationProbe:
    probe = JavaProductionCompilationProbe(**value)
    verify_java_production_compilation_probe_receipt(probe)
    return probe


def run_java_production_compilation_probe(
    *,
    bundle: SourceBundle,
    store,
    source_index: JavaSourceIndex,
    probe: JavaProductionCompilationProbe,
    javac_executable: Path,
    source_entry_ids: dict[str, str],
    compilation_work_root: Path | None = None,
) -> JavaProductionCompilerReport:
    """Compile exact local bytes once and expose only normalized public evidence."""

    verify_java_production_compilation_probe(probe, javac_executable)
    documents = {
        item.relative_path.replace("\\", "/"): item for item in bundle.documents
    }
    indexed_units = {item.source_unit_id for item in source_index.declarations}
    if indexed_units - set(documents) or set(documents) != set(source_entry_ids):
        raise ValueError(
            "compiler source-entry bindings do not close the source bundle"
        )
    source_rows = tuple(
        (path, documents[path].bytes_hash, source_entry_ids[path])
        for path in sorted(documents)
    )
    source_manifest_hash = content_hash(source_rows)
    compilation_run_hash = content_hash(
        {
            "compiler_identity_hash": probe.compiler_identity_hash,
            "source_manifest_hash": source_manifest_hash,
            "source_index_hash": source_index.index_hash,
        }
    )
    raw_by_unit = {}
    context = (
        tempfile.TemporaryDirectory(prefix="m336f-production-javac-")
        if compilation_work_root is None
        else nullcontext(str(compilation_work_root))
    )
    with context as temporary:
        root = Path(temporary)
        if (
            compilation_work_root is not None
            and root.exists()
            and (not root.is_dir() or any(root.iterdir()))
        ):
            raise ValueError("production compiler work root is not empty")
        root.mkdir(parents=True, exist_ok=True)
        source_root = root / "sources"
        classes = root / "classes"
        source_root.mkdir()
        classes.mkdir()
        for source_unit_id in sorted(documents):
            relative = _safe_relative_source_path(source_unit_id)
            raw = store.get_blob(documents[source_unit_id].bytes_hash)
            raw.decode("utf-8", errors="strict")
            target = source_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            raw_by_unit[source_unit_id] = raw
        argument_file = root / "sources.args"
        argument_file.write_text(
            "".join(
                f'"{source_root.joinpath(*_safe_relative_source_path(path).parts).as_posix()}"\n'
                for path in sorted(documents)
            ),
            encoding="utf-8",
            newline="\n",
        )
        command = java_production_compiler_command(
            javac_executable=javac_executable,
            probe=probe,
            compilation_work_root=root,
        )
        completed = subprocess.run(
            command,
            cwd=source_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_compiler_environment(),
        )
    diagnostics = []
    malformed_hashes = []
    ambiguous_path_occurrences: Counter[tuple[str, int, int, str, str]] = Counter()
    for line in completed.stderr.splitlines():
        match = _DIAGNOSTIC.match(line)
        if match is None:
            if line and not _SUMMARY.match(line) and not _NOTE.match(line):
                malformed_hashes.append(content_hash(("JAVAC_OUTPUT", line)))
            continue
        line_number = int(match.group("line"))
        column_number = int(match.group("column"))
        diagnostic_code = match.group("code")
        diagnostic_payload = match.group("payload") or ""
        occurrence_key = (
            match.group("path"),
            line_number,
            column_number,
            diagnostic_code,
            diagnostic_payload,
        )
        occurrence_index = ambiguous_path_occurrences[occurrence_key]
        ambiguous_path_occurrences[occurrence_key] += 1
        source_unit_id = _canonical_reported_path(
            match.group("path"),
            documents,
            raw_by_unit=raw_by_unit,
            line=line_number,
            diagnostic_payload=diagnostic_payload,
            occurrence_index=occurrence_index,
        )
        raw = raw_by_unit.get(source_unit_id or "")
        position = byte_start = byte_end = None
        if raw is not None:
            try:
                position, byte_start, byte_end = utf16_line_column_to_utf8_span(
                    raw,
                    line_number,
                    column_number,
                )
            except ValueError:
                source_unit_id = None
        body = {
            "source_entry_id": source_entry_ids.get(source_unit_id or ""),
            "source_unit_id": source_unit_id,
            "source_unit_identity": (
                content_hash((source_unit_id, documents[source_unit_id].bytes_hash))
                if source_unit_id is not None
                else None
            ),
            "diagnostic_code": diagnostic_code,
            "normalized_category": normalize_java_compiler_diagnostic(diagnostic_code),
            "diagnostic_kind": ("WARNING" if ".warn." in diagnostic_code else "ERROR"),
            "line": line_number,
            "column": column_number,
            "canonical_position": position,
            "canonical_byte_start": byte_start,
            "canonical_byte_end": byte_end,
        }
        diagnostics.append(
            JavaCompilerDiagnostic(**body, diagnostic_hash=content_hash(body))
        )
    ordered_diagnostics = tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.source_unit_id or "",
                item.canonical_byte_start
                if item.canonical_byte_start is not None
                else -1,
                item.diagnostic_code,
                item.diagnostic_hash,
            ),
        )
    )
    bindings = tuple(
        _bind_diagnostic(
            diagnostic,
            compilation_run_hash=compilation_run_hash,
            source_index=source_index,
            raw_by_unit=raw_by_unit,
        )
        for diagnostic in ordered_diagnostics
    )
    error_count = sum(item.diagnostic_kind == "ERROR" for item in ordered_diagnostics)
    warning_count = len(ordered_diagnostics) - error_count
    body = {
        "schema_version": 2,
        "compiler_policy_version": probe.policy_version,
        "compiler_identity_hash": probe.compiler_identity_hash,
        "compilation_run_hash": compilation_run_hash,
        "source_manifest_hash": source_manifest_hash,
        "source_file_count": len(documents),
        "diagnostic_count": len(ordered_diagnostics),
        "error_count": error_count,
        "warning_count": warning_count,
        "unknown_scope_count": sum(
            item.diagnostic_scope is JavaDiagnosticScope.UNKNOWN_SCOPE
            for item in bindings
        ),
        "unmapped_diagnostic_count": sum(not item.declaration_ids for item in bindings),
        "source_unit_unbound_count": sum(
            item.source_unit_id is None for item in ordered_diagnostics
        ),
        "malformed_output_count": len(malformed_hashes),
        "malformed_output_hashes": tuple(sorted(malformed_hashes)),
        "process_exit_code": completed.returncode,
        "diagnostics": ordered_diagnostics,
        "bindings": bindings,
    }
    return JavaProductionCompilerReport(**body, report_hash=content_hash(body))


def java_production_compiler_command(
    *,
    javac_executable: Path,
    probe: JavaProductionCompilationProbe,
    compilation_work_root: Path,
) -> tuple[str, ...]:
    root = compilation_work_root.resolve(strict=False)
    return (
        str(javac_executable.resolve(strict=True)),
        "-J-Duser.language=en",
        "-J-Duser.country=US",
        "--release",
        str(probe.release),
        "-encoding",
        probe.encoding,
        "-proc:none",
        "-Xlint:none",
        "-XDrawDiagnostics",
        "-Xmaxerrs",
        "100000",
        "-Xmaxwarns",
        "100000",
        "-d",
        str(root / "classes"),
        f"@{root / 'sources.args'}",
    )


def build_java_compilation_trust_gate(
    report: JavaProductionCompilerReport,
    source_index: JavaSourceIndex,
) -> JavaCompilationTrustGate:
    declarations = declaration_by_node_id(source_index)
    by_unit = {}
    by_receiver = {}
    for declaration in source_index.declarations:
        if declaration.member_kind in _CALLABLE_KINDS:
            by_unit.setdefault(declaration.source_unit_id, set()).add(
                declaration.node_id
            )
            by_receiver.setdefault(declaration.receiver_type, set()).add(
                declaration.node_id
            )
    blocked = {}
    batch_blocked = bool(
        report.malformed_output_count
        or report.source_unit_unbound_count
        or (
            report.process_exit_code != 0
            and report.error_count == 0
            and report.diagnostic_count == 0
        )
    )
    for binding in report.bindings:
        affected = set()
        if binding.diagnostic_scope is JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING:
            affected.update(
                identifier
                for identifier in binding.declaration_ids
                if declarations[identifier].member_kind in _CALLABLE_KINDS
            )
        elif (
            binding.diagnostic_scope is JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
            and binding.normalized_category != "UNRESOLVED_TYPE"
        ):
            for identifier in binding.declaration_ids:
                affected.update(
                    by_receiver.get(declarations[identifier].receiver_type, ())
                )
        elif binding.diagnostic_scope is JavaDiagnosticScope.UNKNOWN_SCOPE or (
            binding.diagnostic_scope is JavaDiagnosticScope.AMBIENT_FILE
            and binding.normalized_category in _AMBIENT_BLOCKING_CATEGORIES
        ):
            affected.update(by_unit.get(binding.source_unit_id, ()))
        for declaration_id in affected:
            blocked.setdefault(declaration_id, set()).add(binding.diagnostic_hash)
    policy_body = {
        "version": M336F_DIAGNOSTIC_BINDING_VERSION,
        "header_blocks": True,
        "enclosing_type_blocks": True,
        "enclosing_unresolved_type_blocks": False,
        "body_only_blocks": False,
        "unrelated_blocks": False,
        "ambient_blocking_categories": tuple(sorted(_AMBIENT_BLOCKING_CATEGORIES)),
        "unknown_known_unit_blocks": True,
        "unbound_or_malformed_blocks_batch": True,
        "silent_nonzero_exit_blocks_batch": True,
    }
    rows = tuple(
        (identifier, tuple(sorted(hashes)))
        for identifier, hashes in sorted(blocked.items())
    )
    body = {
        "schema_version": 1,
        "compiler_report_hash": report.report_hash,
        "compilation_policy_hash": content_hash(policy_body),
        "blocked_declaration_ids": tuple(identifier for identifier, _hashes in rows),
        "applicable_blocking_diagnostic_hashes": rows,
        "batch_blocked": batch_blocked,
        "blocked_declaration_count": len(rows),
    }
    return JavaCompilationTrustGate(**body, gate_hash=content_hash(body))


def verify_java_production_compiler_report(
    report: JavaProductionCompilerReport,
) -> None:
    for diagnostic in report.diagnostics:
        body = asdict(diagnostic)
        claimed = body.pop("diagnostic_hash")
        if content_hash(body) != claimed:
            raise ValueError("Java compiler diagnostic hash mismatch")
    diagnostic_hashes = {item.diagnostic_hash for item in report.diagnostics}
    for binding in report.bindings:
        body = asdict(binding)
        claimed = body.pop("binding_hash")
        if (
            content_hash(body) != claimed
            or binding.compilation_run_hash != report.compilation_run_hash
            or binding.diagnostic_hash not in diagnostic_hashes
        ):
            raise ValueError("declaration diagnostic binding hash mismatch")
    if len(report.bindings) != len(report.diagnostics):
        raise ValueError("every Java compiler diagnostic requires exactly one binding")
    for diagnostic, binding in zip(report.diagnostics, report.bindings, strict=True):
        if (
            binding.diagnostic_hash != diagnostic.diagnostic_hash
            or binding.source_entry_id != diagnostic.source_entry_id
            or binding.source_unit_id != diagnostic.source_unit_id
            or binding.source_unit_identity != diagnostic.source_unit_identity
            or binding.compiler_diagnostic_code != diagnostic.diagnostic_code
            or binding.normalized_category != diagnostic.normalized_category
            or binding.canonical_position != diagnostic.canonical_position
            or binding.canonical_byte_start != diagnostic.canonical_byte_start
            or binding.canonical_byte_end != diagnostic.canonical_byte_end
        ):
            raise ValueError("Java compiler diagnostic and binding differ")
    body = asdict(report)
    claimed = body.pop("report_hash")
    if (
        content_hash(body) != claimed
        or report.schema_version != 2
        or report.compiler_policy_version != M336F_COMPILER_POLICY_VERSION
        or report.diagnostic_count != len(report.diagnostics)
        or report.error_count
        != sum(item.diagnostic_kind == "ERROR" for item in report.diagnostics)
        or report.warning_count
        != sum(item.diagnostic_kind == "WARNING" for item in report.diagnostics)
        or report.error_count + report.warning_count != report.diagnostic_count
        or report.source_file_count <= 0
        or (report.error_count > 0 and report.process_exit_code == 0)
        or report.unknown_scope_count
        != sum(
            item.diagnostic_scope is JavaDiagnosticScope.UNKNOWN_SCOPE
            for item in report.bindings
        )
        or report.unmapped_diagnostic_count
        != sum(not item.declaration_ids for item in report.bindings)
        or report.source_unit_unbound_count
        != sum(item.source_unit_id is None for item in report.diagnostics)
        or report.malformed_output_count != len(report.malformed_output_hashes)
    ):
        raise ValueError("Java production compiler report mismatch")


def verify_java_compilation_trust_gate(
    gate: JavaCompilationTrustGate,
    report: JavaProductionCompilerReport,
    source_index: JavaSourceIndex,
) -> None:
    verify_java_production_compiler_report(report)
    if gate != build_java_compilation_trust_gate(report, source_index):
        raise ValueError("Java compilation trust gate mismatch")


def java_production_compiler_report_from_dict(
    value: dict,
) -> JavaProductionCompilerReport:
    diagnostics = tuple(JavaCompilerDiagnostic(**item) for item in value["diagnostics"])
    bindings = tuple(
        DeclarationDiagnosticBinding(
            **{
                **item,
                "declaration_ids": tuple(item["declaration_ids"]),
                "diagnostic_scope": JavaDiagnosticScope(item["diagnostic_scope"]),
            }
        )
        for item in value["bindings"]
    )
    report = JavaProductionCompilerReport(
        **{
            **value,
            "malformed_output_hashes": tuple(value["malformed_output_hashes"]),
            "diagnostics": diagnostics,
            "bindings": bindings,
        }
    )
    verify_java_production_compiler_report(report)
    return report


def java_compilation_trust_gate_from_dict(value: dict) -> JavaCompilationTrustGate:
    return JavaCompilationTrustGate(
        **{
            **value,
            "blocked_declaration_ids": tuple(value["blocked_declaration_ids"]),
            "applicable_blocking_diagnostic_hashes": tuple(
                (item[0], tuple(item[1]))
                for item in value["applicable_blocking_diagnostic_hashes"]
            ),
        }
    )


def utf16_line_column_to_utf8_span(
    raw: bytes, line: int, column: int
) -> tuple[int, int, int]:
    """Map one-based javac UTF-16 line/column to canonical UTF-8 byte offsets."""

    return _utf16_line_column_to_utf8_span(raw, line, column, canonical_newlines=True)


def normalize_java_compiler_diagnostic(code: str) -> str:
    if "cant.resolve" in code or "doesnt.exist" in code:
        return "UNRESOLVED_TYPE"
    if "duplicate.class" in code or "name.clash" in code:
        return "DUPLICATE_SIGNATURE"
    if "package.not.visible" in code or "not.in.module.on.module.source.path" in code:
        return "NON_EXPORTED_MODULE_PACKAGE"
    if "not.def.access" in code or "not.public.cant.access" in code:
        return "INACCESSIBLE_TYPE"
    if "expected" in code or "illegal.start" in code or "premature.eof" in code:
        return "MALFORMED_GENERIC_DECLARATION"
    return "COMPILER_ERROR"


def _bind_diagnostic(
    diagnostic: JavaCompilerDiagnostic,
    *,
    compilation_run_hash: str,
    source_index: JavaSourceIndex,
    raw_by_unit: dict[str, bytes],
) -> DeclarationDiagnosticBinding:
    unit = diagnostic.source_unit_id
    start = diagnostic.canonical_byte_start
    end = diagnostic.canonical_byte_end
    declarations = tuple(
        item for item in source_index.declarations if item.source_unit_id == unit
    )
    raw_start = raw_end = None
    if (
        unit is not None
        and diagnostic.line is not None
        and diagnostic.column is not None
    ):
        try:
            _position, raw_start, raw_end = _utf16_line_column_to_utf8_span(
                raw_by_unit[unit],
                diagnostic.line,
                diagnostic.column,
                canonical_newlines=False,
            )
        except (KeyError, ValueError):
            raw_start = raw_end = None
    overlapping = tuple(
        item
        for item in declarations
        if raw_start is not None
        and raw_end is not None
        and raw_start < item.declaration_span.byte_end
        and max(raw_end, raw_start + 1) > item.declaration_span.byte_start
    )
    scope = JavaDiagnosticScope.AMBIENT_FILE
    identifiers = ()
    enclosing = None
    if unit is None or start is None:
        scope = JavaDiagnosticScope.UNKNOWN_SCOPE
    elif overlapping:
        callables = tuple(
            item for item in overlapping if item.member_kind in _CALLABLE_KINDS
        )
        unrelated_members = tuple(
            item
            for item in overlapping
            if item.member_kind not in _CALLABLE_KINDS | _TYPE_KINDS
        )
        types = tuple(item for item in overlapping if item.member_kind in _TYPE_KINDS)
        if callables:
            smallest = min(
                callables,
                key=lambda item: (
                    item.declaration_span.byte_end - item.declaration_span.byte_start
                ),
            )
            raw = raw_by_unit[unit]
            body_start = _declaration_body_start(
                raw,
                smallest.declaration_span.byte_start,
                smallest.declaration_span.byte_end,
            )
            scope = (
                JavaDiagnosticScope.BODY_ONLY
                if body_start is not None and raw_start > body_start
                else JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING
            )
            identifiers = (smallest.node_id,)
            enclosing = content_hash(("JAVA_TYPE", smallest.receiver_type))
        elif unrelated_members:
            smallest = min(
                unrelated_members,
                key=lambda item: (
                    item.declaration_span.byte_end - item.declaration_span.byte_start
                ),
            )
            scope = JavaDiagnosticScope.UNRELATED_DECLARATION
            identifiers = (smallest.node_id,)
            enclosing = content_hash(("JAVA_TYPE", smallest.receiver_type))
        elif types:
            smallest = min(
                types,
                key=lambda item: (
                    item.declaration_span.byte_end - item.declaration_span.byte_start
                ),
            )
            scope = JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
            identifiers = (smallest.node_id,)
            enclosing = content_hash(("JAVA_TYPE", smallest.receiver_type))
        else:
            scope = JavaDiagnosticScope.UNRELATED_DECLARATION
            identifiers = tuple(sorted(item.node_id for item in overlapping))
    body = {
        "compilation_run_hash": compilation_run_hash,
        "diagnostic_hash": diagnostic.diagnostic_hash,
        "source_entry_id": diagnostic.source_entry_id,
        "source_unit_id": unit,
        "source_unit_identity": diagnostic.source_unit_identity,
        "compiler_diagnostic_code": diagnostic.diagnostic_code,
        "normalized_category": diagnostic.normalized_category,
        "canonical_position": diagnostic.canonical_position,
        "canonical_byte_start": start,
        "canonical_byte_end": end,
        "declaration_ids": identifiers,
        "diagnostic_scope": scope,
        "enclosing_type_identity": enclosing,
    }
    return DeclarationDiagnosticBinding(**body, binding_hash=content_hash(body))


def _safe_relative_source_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or path.suffix != ".java"
    ):
        raise ValueError("compiler source-unit path is not canonical and relative")
    return path


def _canonical_reported_path(
    value: str,
    documents: dict[str, object],
    *,
    raw_by_unit: dict[str, bytes] | None = None,
    line: int | None = None,
    diagnostic_payload: str = "",
    occurrence_index: int = 0,
) -> str | None:
    normalized = value.replace("\\", "/")
    if normalized in documents:
        return normalized
    matches = tuple(
        path
        for path in documents
        if path.endswith("/" + normalized) or normalized.endswith("/" + path)
    )
    if len(matches) == 1:
        return matches[0]
    if not matches or raw_by_unit is None or line is None:
        return None
    payload_tokens = {
        token
        for token in re.findall(r"[A-Za-z_$][\w.$]*", diagnostic_payload)
        if token not in {"class", "interface", "kindname", "location"}
    }
    tokens = tuple(
        sorted(
            payload_tokens
            | {token.rsplit(".", 1)[-1] for token in payload_tokens if "." in token},
            key=lambda item: (-len(item), item),
        )
    )
    scored = []
    for path in matches:
        lines = raw_by_unit[path].decode("utf-8", errors="strict").splitlines()
        if line > len(lines):
            continue
        source_line = lines[line - 1]
        score = sum(len(token) for token in tokens if token in source_line)
        scored.append((score, path))
    if not scored:
        return None
    best_score = max(score for score, _path in scored)
    if best_score == 0:
        return None
    best = tuple(sorted(path for score, path in scored if score == best_score))
    return best[occurrence_index] if occurrence_index < len(best) else None


def _compiler_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("CLASSPATH", None)
    environment.pop("JAVA_TOOL_OPTIONS", None)
    environment.pop("JDK_JAVA_OPTIONS", None)
    return environment


def _utf16_line_column_to_utf8_span(
    raw: bytes,
    line: int,
    column: int,
    *,
    canonical_newlines: bool,
) -> tuple[int, int, int]:
    if line < 1 or column < 1:
        raise ValueError("compiler position is not one-based")
    original = raw.decode("utf-8", errors="strict")
    original_lines = original.splitlines(keepends=True)
    if line > len(original_lines):
        raise ValueError("compiler line escapes source")
    current = original_lines[line - 1].rstrip("\r\n")
    wanted_units = column - 1
    consumed_units = 0
    character_index = 0
    for character_index, character in enumerate(current):
        units = (
            8 - (consumed_units % 8)
            if character == "\t"
            else len(character.encode("utf-16-le")) // 2
        )
        if consumed_units == wanted_units:
            break
        if consumed_units + units > wanted_units:
            raise ValueError(
                "compiler column bisects tab expansion"
                if character == "\t"
                else "compiler column bisects a non-BMP character"
            )
        consumed_units += units
    else:
        character_index = len(current)
    if consumed_units != wanted_units:
        raise ValueError("compiler column escapes source line")
    if canonical_newlines:
        prefix = (
            "".join(original_lines[: line - 1])
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
    else:
        prefix = "".join(original_lines[: line - 1])
    before = prefix + current[:character_index]
    canonical_position = len(before)
    byte_start = len(before.encode("utf-8"))
    byte_end = (
        byte_start
        if character_index == len(current)
        else byte_start + len(current[character_index].encode("utf-8"))
    )
    return canonical_position, byte_start, byte_end


def _declaration_body_start(raw: bytes, start: int, end: int) -> int | None:
    """Find a callable's body brace without mistaking annotation array braces."""

    index = start
    parentheses = brackets = 0
    quote = None
    while index < end:
        current = raw[index]
        following = raw[index + 1] if index + 1 < end else None
        if quote is not None:
            if current == 92:  # backslash
                index += 2
                continue
            if current == quote:
                quote = None
            index += 1
            continue
        if current in (34, 39):  # string or character literal
            quote = current
        elif current == 47 and following == 47:  # line comment
            newline = raw.find(b"\n", index + 2, end)
            index = end if newline < 0 else newline + 1
            continue
        elif current == 47 and following == 42:  # block comment
            close = raw.find(b"*/", index + 2, end)
            index = end if close < 0 else close + 2
            continue
        elif current == 40:
            parentheses += 1
        elif current == 41:
            parentheses = max(0, parentheses - 1)
        elif current == 91:
            brackets += 1
        elif current == 93:
            brackets = max(0, brackets - 1)
        elif current == 123 and not parentheses and not brackets:
            return index
        index += 1
    return None
