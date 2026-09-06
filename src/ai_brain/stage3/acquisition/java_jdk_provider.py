"""Frozen evaluator-only JDK provider identity for the M-33.6 Java freeze."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_release import JAVA_TARGET_RELEASE

M336_JDK_PROVIDER_SCHEMA_VERSION = 1
M336_JAVAC_INVOCATION_POLICY = (
    "-proc:none",
    "-encoding",
    "UTF-8",
    "--release",
    str(JAVA_TARGET_RELEASE),
)
M336_PUBLIC_COMPILER_DIAGNOSTIC_POLICY = "m336f.production-javac-diagnostics.v2"


@dataclass(frozen=True)
class M336JdkPlatformIdentity:
    platform: str
    vendor: str
    version: str
    build: str
    distribution_archive_sha256: str
    java_sha256: str
    javac_sha256: str
    release_file_sha256: str


@dataclass(frozen=True)
class M336JdkProviderManifest:
    schema_version: int
    provider_id: str
    target_release: int
    javac_invocation_policy: tuple[str, ...]
    platforms: tuple[M336JdkPlatformIdentity, ...]
    manifest_hash: str


@dataclass(frozen=True)
class M336JdkVerificationReceipt:
    provider_manifest_hash: str
    platform: str
    java_path: str
    javac_path: str
    release_path: str
    observed_version_banner: tuple[str, ...]
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336PrivateJdkObservation:
    contract_role: str
    platform: str
    java_executable: Path
    javac_executable: Path
    release_file: Path
    provider_installation_root: Path
    observed_version_banner: tuple[str, ...]


@dataclass(frozen=True)
class M336PublicJdkIdentityReceipt:
    schema_version: int
    contract_role: str
    provider_manifest_hash: str
    provider_id: str
    platform_role: str
    target_java_release: int
    invocation_policy_hash: str
    semantic_compiler_identity_hash: str
    expected_vendor: str
    expected_version: str
    expected_build: str
    observed_java_binary_hash: str
    observed_javac_binary_hash: str
    observed_release_file_hash: str
    normalized_version_banner_hash: str
    verification_status: str
    receipt_hash: str


def frozen_m336_jdk_provider_manifest() -> M336JdkProviderManifest:
    """Return the pre-source, platform-specific Microsoft OpenJDK 21 binding."""

    platforms = (
        M336JdkPlatformIdentity(
            platform="karina",
            vendor="Microsoft",
            version="21.0.11",
            build="21.0.11+10-LTS/Microsoft-13877187",
            distribution_archive_sha256=(
                "1d58b1335d019bfe1c7c56979c927d0f51222c6dd41c33772d8396ea6cd409c1"
            ),
            java_sha256=(
                "33cb6bc705a5c7e6ed16aed1b149c61802a787cfe8f2868b651d596c82a4c4a6"
            ),
            javac_sha256=(
                "729af9d119492aa44957e3138dcae029ed08e10b06a33cb23a879d7819bb8740"
            ),
            release_file_sha256=(
                "4ffc87a948c01a9fb035ded3b626c7987ff13a6c94bafcd59f64bbe3cbd2fa45"
            ),
        ),
        M336JdkPlatformIdentity(
            platform="windows",
            vendor="Microsoft",
            version="21.0.11",
            build="21.0.11+10-LTS/Microsoft-13877171",
            distribution_archive_sha256=(
                "a58466dc0c0edd9740b5c5db10d95a70b682cb04f1a5101479d75e844f7160ff"
            ),
            java_sha256=(
                "e4c702ab4d11cc094144ff91c91371ed9b35a38a2e54ed1e032a628cc5bd40f3"
            ),
            javac_sha256=(
                "43ed8ede602fe115d7690463f98ad651abade9041b0bbe9f11825d8f0a499475"
            ),
            release_file_sha256=(
                "60b10f15dddd3854328ddfe731457f33a67ff86a515edf92d44fda5a4ed427eb"
            ),
        ),
    )
    body = {
        "schema_version": M336_JDK_PROVIDER_SCHEMA_VERSION,
        "provider_id": "m336.microsoft-openjdk-21.0.11+10",
        "target_release": JAVA_TARGET_RELEASE,
        "javac_invocation_policy": M336_JAVAC_INVOCATION_POLICY,
        "platforms": platforms,
    }
    return M336JdkProviderManifest(**body, manifest_hash=content_hash(body))


def m336_public_compiler_semantic_identity_hash() -> str:
    """Bind compiler semantics without binding any one host filesystem path."""

    manifest = frozen_m336_jdk_provider_manifest()
    versions = {item.version for item in manifest.platforms}
    if len(versions) != 1:
        raise ValueError("accepted JDK platforms do not share compiler semantics")
    version = next(iter(versions))
    return content_hash(
        {
            "policy_version": M336_PUBLIC_COMPILER_DIAGNOSTIC_POLICY,
            "provider_manifest_hash": manifest.manifest_hash,
            "javac_version": f"javac {version}",
            "release": manifest.target_release,
            "encoding": "UTF-8",
            "annotation_processing": False,
            "locale_policy": "JAVAC_XDRAWDIAGNOSTICS_EN_US",
            "classpath_manifest_hash": content_hash(()),
        }
    )


def verify_m336_jdk_provider_evidence(
    *, platform: str, java: Path, javac: Path
) -> tuple[M336PrivateJdkObservation, M336PublicJdkIdentityReceipt]:
    """Return private paths separately from a path-free public identity receipt."""

    manifest = frozen_m336_jdk_provider_manifest()
    expected = next(
        (item for item in manifest.platforms if item.platform == platform), None
    )
    if expected is None:
        raise ValueError("unknown M-33.6 JDK platform")
    resolved_java = java.resolve(strict=True)
    resolved_javac = javac.resolve(strict=True)
    release = (resolved_java.parent.parent / "release").resolve(strict=True)
    observed = (
        bytes_hash(resolved_java.read_bytes()),
        bytes_hash(resolved_javac.read_bytes()),
        bytes_hash(release.read_bytes()),
    )
    required = (
        expected.java_sha256,
        expected.javac_sha256,
        expected.release_file_sha256,
    )
    if observed != required:
        raise ValueError("JDK executable/release identity differs from frozen provider")
    result = subprocess.run(
        (str(resolved_java), "-version"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    banner = tuple(
        item.strip()
        for item in (result.stderr or result.stdout).splitlines()
        if item.strip()
    )
    joined = "\n".join(banner)
    if expected.version not in joined or expected.build.split("/")[0] not in joined:
        raise ValueError("JDK version banner differs from frozen provider")
    private = M336PrivateJdkObservation(
        contract_role="PRIVATE_HOST_OBSERVATION",
        platform=platform,
        java_executable=resolved_java,
        javac_executable=resolved_javac,
        release_file=release,
        provider_installation_root=resolved_java.parent.parent,
        observed_version_banner=banner,
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_PLATFORM_TELEMETRY",
        "provider_manifest_hash": manifest.manifest_hash,
        "provider_id": manifest.provider_id,
        "platform_role": platform,
        "target_java_release": manifest.target_release,
        "invocation_policy_hash": content_hash(manifest.javac_invocation_policy),
        "semantic_compiler_identity_hash": (
            m336_public_compiler_semantic_identity_hash()
        ),
        "expected_vendor": expected.vendor,
        "expected_version": expected.version,
        "expected_build": expected.build,
        "observed_java_binary_hash": observed[0],
        "observed_javac_binary_hash": observed[1],
        "observed_release_file_hash": observed[2],
        "normalized_version_banner_hash": content_hash(banner),
        "verification_status": "PASS",
    }
    public = M336PublicJdkIdentityReceipt(**body, receipt_hash=content_hash(body))
    return private, public


def verify_m336_jdk_provider(
    *, platform: str, java: Path, javac: Path
) -> M336JdkVerificationReceipt:
    private, public = verify_m336_jdk_provider_evidence(
        platform=platform, java=java, javac=javac
    )
    body = {
        "provider_manifest_hash": public.provider_manifest_hash,
        "platform": platform,
        "java_path": str(private.java_executable),
        "javac_path": str(private.javac_executable),
        "release_path": str(private.release_file),
        "observed_version_banner": private.observed_version_banner,
        "status": "PASS",
    }
    return M336JdkVerificationReceipt(**body, receipt_hash=content_hash(body))
