"""Frozen Java release identity shared by production and evaluation gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_type_universe import load_java21_inventory

JAVA_TARGET_RELEASE = 21
JAVA_RELEASE_POLICY_VERSION = "m344.java-release-consistency.v1"


@dataclass(frozen=True)
class JavaReleaseIdentity:
    source_compatibility_release: int
    javac_release: int
    ct_sym_release: int
    symbol_inventory_release: int
    module_export_model_release: int
    oracle_release: int
    diagnostics_provider_release: int
    evaluation_config_release: int
    policy_version: str
    platform_inventory_hash: str
    identity_hash: str


@dataclass(frozen=True)
class JavaReleaseConsistencyReport:
    releases: tuple[int, ...]
    expected_release: int
    all_equal: bool
    status: str
    report_hash: str


def frozen_java_release_identity() -> JavaReleaseIdentity:
    inventory, _symbols = load_java21_inventory()
    body = {
        "source_compatibility_release": JAVA_TARGET_RELEASE,
        "javac_release": JAVA_TARGET_RELEASE,
        "ct_sym_release": inventory.release,
        "symbol_inventory_release": inventory.release,
        "module_export_model_release": inventory.release,
        "oracle_release": JAVA_TARGET_RELEASE,
        "diagnostics_provider_release": JAVA_TARGET_RELEASE,
        "evaluation_config_release": JAVA_TARGET_RELEASE,
        "policy_version": JAVA_RELEASE_POLICY_VERSION,
        "platform_inventory_hash": inventory.manifest_hash,
    }
    return JavaReleaseIdentity(**body, identity_hash=content_hash(body))


def verify_java_release_identity(identity: JavaReleaseIdentity) -> None:
    body = asdict(identity)
    claimed = body.pop("identity_hash")
    if content_hash(body) != claimed:
        raise ValueError("Java release identity hash mismatch")
    inventory, _symbols = load_java21_inventory()
    if identity.platform_inventory_hash != inventory.manifest_hash:
        raise ValueError("Java release identity uses another symbol inventory")
    report = evaluate_java_release_consistency(identity)
    if report.status != "PASS":
        raise ValueError("Java release identity is inconsistent")


def evaluate_java_release_consistency(
    *identities: JavaReleaseIdentity,
) -> JavaReleaseConsistencyReport:
    if not identities:
        raise ValueError("Java release consistency requires an identity")
    releases = tuple(
        value
        for identity in identities
        for value in (
            identity.source_compatibility_release,
            identity.javac_release,
            identity.ct_sym_release,
            identity.symbol_inventory_release,
            identity.module_export_model_release,
            identity.oracle_release,
            identity.diagnostics_provider_release,
            identity.evaluation_config_release,
        )
    )
    all_equal = bool(releases) and set(releases) == {JAVA_TARGET_RELEASE}
    body = {
        "releases": releases,
        "expected_release": JAVA_TARGET_RELEASE,
        "all_equal": all_equal,
        "status": "PASS" if all_equal else "FAIL",
    }
    return JavaReleaseConsistencyReport(**body, report_hash=content_hash(body))
