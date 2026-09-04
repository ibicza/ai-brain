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


def verify_m336_jdk_provider(
    *, platform: str, java: Path, javac: Path
) -> M336JdkVerificationReceipt:
    manifest = frozen_m336_jdk_provider_manifest()
    expected = next(
        (item for item in manifest.platforms if item.platform == platform), None
    )
    if expected is None:
        raise ValueError("unknown M-33.6 JDK platform")
    java = java.resolve(strict=True)
    javac = javac.resolve(strict=True)
    release = (java.parent.parent / "release").resolve(strict=True)
    observed = (
        bytes_hash(java.read_bytes()),
        bytes_hash(javac.read_bytes()),
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
        (str(java), "-version"),
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
    body = {
        "provider_manifest_hash": manifest.manifest_hash,
        "platform": platform,
        "java_path": str(java),
        "javac_path": str(javac),
        "release_path": str(release),
        "observed_version_banner": banner,
        "status": "PASS",
    }
    return M336JdkVerificationReceipt(**body, receipt_hash=content_hash(body))
