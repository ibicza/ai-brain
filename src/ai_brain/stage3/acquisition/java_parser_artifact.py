"""Runtime verification of the exact pinned Tree-sitter Java wheel payload."""

from __future__ import annotations

import importlib.metadata
import platform
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_java
from tree_sitter import Language

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

TREE_SITTER_VERSION = "0.25.2"
TREE_SITTER_JAVA_VERSION = "0.23.5"
TREE_SITTER_JAVA_SOURCE_SHA256 = (
    "f5cd57b8f1270a7f0438878750d02ccc79421d45cca65ff284f1527e9ef02e38"
)
TREE_SITTER_JAVA_BINDING_C_SHA256 = (
    "f62d846c352e0cc50b1c261f01b94583d5ef3b04a9c62a8ce60d60359a6ea33b"
)
TREE_SITTER_JAVA_ABI = 14

_COMMON = (
    (
        "__init__.py",
        "ef10da4947ee5567ad296494d9051d1f1a2b1abd5e40ab1720584f17ff4efac0",
        819,
    ),
    (
        "__init__.pyi",
        "a0f8fab5449fa47334f1b4e6104e63e42da66c730158d90cf0eba130673954c8",
        109,
    ),
    ("binding.c", TREE_SITTER_JAVA_BINDING_C_SHA256, 679),
    ("py.typed", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", 0),
    (
        "queries/highlights.scm",
        "576c0df8df0b116cd642140ddc508c01f9d3283582afd8581c1f35caf4d71386",
        2064,
    ),
    (
        "queries/tags.scm",
        "bcb22147b8582d92743fc973864cefb894a4c12b3957f16f3d472b2ec7cd4c49",
        499,
    ),
)
_PLATFORMS = {
    ("Windows", "AMD64"): (
        "1ee45e790f8d31d416bc84a09dac2e2c6bc343e89b8a2e1d550513498eedfde7",
        "_binding.pyd",
        "1e2701354844067b291d9405be998d69291892fcfb75ca6b1c314fd3caa5aca9",
        422400,
    ),
    ("Linux", "x86_64"): (
        "370b204b9500b847f6d0c5ad584045831cee69e9a3e4d878535d39e4a7e4c4f1",
        "_binding.abi3.so",
        "766dcdc998aaccd38fe8fe34a2eeb795768231e2df9ef00d429181e3120995c3",
        509984,
    ),
}


@dataclass(frozen=True)
class JavaParserCommonArtifactManifest:
    schema_version: int
    package_version: str
    parser_runtime_version: str
    grammar_source_artifact_hash: str
    generated_binding_source_hash: str
    grammar_abi: int
    common_payload: tuple[tuple[str, str, int], ...]
    manifest_hash: str


@dataclass(frozen=True)
class JavaParserArtifactManifest:
    common_manifest_hash: str
    platform_system: str
    platform_machine: str
    locked_wheel_hash: str
    native_binding_name: str
    native_binding_hash: str
    native_binding_size: int
    installed_payload_hash: str
    verification_status: str
    manifest_hash: str


def verify_java_parser_artifact() -> tuple[
    JavaParserCommonArtifactManifest, JavaParserArtifactManifest
]:
    if importlib.metadata.version("tree-sitter") != TREE_SITTER_VERSION:
        raise RuntimeError("unpinned tree-sitter runtime")
    if importlib.metadata.version("tree-sitter-java") != TREE_SITTER_JAVA_VERSION:
        raise RuntimeError("unpinned tree-sitter-java distribution")
    language = Language(tree_sitter_java.language())
    if language.abi_version != TREE_SITTER_JAVA_ABI:
        raise RuntimeError("unexpected tree-sitter-java grammar ABI")
    key = (platform.system(), platform.machine())
    expected = _PLATFORMS.get(key)
    if expected is None:
        raise RuntimeError(f"unsupported tree-sitter-java artifact platform: {key}")
    root = Path(tree_sitter_java.__file__).parent
    wheel_hash, binding_name, binding_hash, binding_size = expected
    rows = []
    for relative, expected_hash, expected_size in (*_COMMON, expected[1:]):
        path = root / relative
        actual = (relative, bytes_hash(path.read_bytes()), path.stat().st_size)
        if actual != (relative, expected_hash, expected_size):
            raise RuntimeError(f"tree-sitter-java artifact mismatch: {relative}")
        rows.append(actual)
    common_body = {
        "schema_version": 1,
        "package_version": TREE_SITTER_JAVA_VERSION,
        "parser_runtime_version": TREE_SITTER_VERSION,
        "grammar_source_artifact_hash": TREE_SITTER_JAVA_SOURCE_SHA256,
        "generated_binding_source_hash": TREE_SITTER_JAVA_BINDING_C_SHA256,
        "grammar_abi": TREE_SITTER_JAVA_ABI,
        "common_payload": _COMMON,
    }
    common = JavaParserCommonArtifactManifest(
        **common_body, manifest_hash=content_hash(common_body)
    )
    body = {
        "common_manifest_hash": common.manifest_hash,
        "platform_system": key[0],
        "platform_machine": key[1],
        "locked_wheel_hash": wheel_hash,
        "native_binding_name": binding_name,
        "native_binding_hash": binding_hash,
        "native_binding_size": binding_size,
        "installed_payload_hash": content_hash(tuple(rows)),
        "verification_status": "PASS",
    }
    return common, JavaParserArtifactManifest(**body, manifest_hash=content_hash(body))
