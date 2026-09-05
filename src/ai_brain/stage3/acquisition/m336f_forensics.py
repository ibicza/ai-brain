"""Public-safe exact-R20 diagnostic context classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilationContextObservation:
    diagnostic_present: bool
    diagnostic_code: str | None
    diagnostic_scope: str | None
    compiler_identity_hash: str
    source_unit_binding_valid: bool = True
    normalized_category: str | None = None


def classify_compilation_contexts(
    *,
    current: CompilationContextObservation,
    selected_plus_internal: CompilationContextObservation,
    all_same_root: CompilationContextObservation,
    frozen_classpath: CompilationContextObservation,
) -> str:
    """Classify a disagreement without consulting family/path/target identities."""

    observations = (
        current,
        selected_plus_internal,
        all_same_root,
        frozen_classpath,
    )
    if not all(item.source_unit_binding_valid for item in observations):
        return "DIAGNOSTIC_LOCATION_MAPPING_ERROR"
    if current.compiler_identity_hash != frozen_classpath.compiler_identity_hash:
        return "COMPILER_ENVIRONMENT_MISMATCH"
    if not current.diagnostic_present:
        return "UNRESOLVED"
    if (
        not selected_plus_internal.diagnostic_present
        and not all_same_root.diagnostic_present
        and frozen_classpath.diagnostic_present
        and current.diagnostic_code == frozen_classpath.diagnostic_code
        and current.diagnostic_scope == frozen_classpath.diagnostic_scope
    ):
        return "MISSING_SELECTED_INTERNAL_TYPE"
    if all(item.diagnostic_present for item in observations):
        stable = {
            (item.diagnostic_code, item.diagnostic_scope) for item in observations
        }
        return (
            "GENUINE_SOURCE_DECLARATION_ERROR"
            if len(stable) == 1
            else "MULTIPLE_CAUSES"
        )
    if selected_plus_internal.diagnostic_present and all_same_root.diagnostic_present:
        return "MISSING_EXTERNAL_DEPENDENCY"
    return "MULTIPLE_CAUSES"
