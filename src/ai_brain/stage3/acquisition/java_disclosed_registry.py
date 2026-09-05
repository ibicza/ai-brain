"""Content-addressed append-only disclosed Java material registry."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

DISCLOSED_REGISTRY_SCHEMA_VERSION = 1
DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION = 2
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
DEFAULT_REGISTRY_ROOT = (
    Path(__file__).resolve().parents[4] / "artifacts/acquisition/disclosed_java"
)


@dataclass(frozen=True)
class DisclosedJavaMaterialEntry:
    schema_version: int
    coordinate: str
    version: str
    source_url: str
    archive_hash: str
    pom_hash: str
    raw_source_hashes: tuple[str, ...]
    canonical_source_hashes: tuple[str, ...]
    source_tree_hash: str
    selected_relative_paths: tuple[str, ...]
    selected_path_manifest_hash: str
    declaration_fingerprints: tuple[str, ...]
    scm_revision: str
    correspondence_hash: str
    disclosure_reason: str
    originating_chain: str
    entry_hash: str


@dataclass(frozen=True)
class DisclosedJavaRegistryManifest:
    schema_version: int
    previous_manifest_hash: str | None
    entry_hashes: tuple[str, ...]
    manifest_hash: str


@dataclass(frozen=True)
class DisclosureRegistryAppendReceipt:
    schema_version: int
    previous_registry_manifest_hash: str
    previous_entry_count: int
    appended_entry_hashes: tuple[str, ...]
    appended_entry_count: int
    resulting_entry_count: int
    resulting_manifest_hash: str
    acquisition_run_id: str
    f20_sha: str
    receipt_hash: str


def build_disclosed_java_material_entry(**values) -> DisclosedJavaMaterialEntry:
    body = {
        "schema_version": DISCLOSED_REGISTRY_SCHEMA_VERSION,
        "coordinate": values["coordinate"],
        "version": values["version"],
        "source_url": values["source_url"],
        "archive_hash": values["archive_hash"],
        "pom_hash": values["pom_hash"],
        "raw_source_hashes": tuple(sorted(set(values["raw_source_hashes"]))),
        "canonical_source_hashes": tuple(
            sorted(set(values["canonical_source_hashes"]))
        ),
        "source_tree_hash": values["source_tree_hash"],
        "selected_relative_paths": tuple(
            sorted(set(values["selected_relative_paths"]))
        ),
        "selected_path_manifest_hash": content_hash(
            tuple(sorted(set(values["selected_relative_paths"])))
        ),
        "declaration_fingerprints": tuple(
            sorted(set(values["declaration_fingerprints"]))
        ),
        "scm_revision": values["scm_revision"],
        "correspondence_hash": values["correspondence_hash"],
        "disclosure_reason": values["disclosure_reason"],
        "originating_chain": values["originating_chain"],
    }
    return DisclosedJavaMaterialEntry(**body, entry_hash=content_hash(body))


def dump_disclosed_java_material_entry(entry: DisclosedJavaMaterialEntry) -> bytes:
    verify_disclosed_java_material_entry(entry)
    return (canonical_json(asdict(entry)) + "\n").encode("utf-8")


def load_disclosed_java_material_entry(raw: bytes | str) -> DisclosedJavaMaterialEntry:
    value = _load_json(raw)
    expected = {
        "schema_version",
        "coordinate",
        "version",
        "source_url",
        "archive_hash",
        "pom_hash",
        "raw_source_hashes",
        "canonical_source_hashes",
        "source_tree_hash",
        "selected_relative_paths",
        "selected_path_manifest_hash",
        "declaration_fingerprints",
        "scm_revision",
        "correspondence_hash",
        "disclosure_reason",
        "originating_chain",
        "entry_hash",
    }
    _fields(value, expected, "disclosed material entry")
    for key in (
        "raw_source_hashes",
        "canonical_source_hashes",
        "selected_relative_paths",
        "declaration_fingerprints",
    ):
        if not isinstance(value[key], list):
            raise TypeError(f"{key} must be an array")
        value[key] = tuple(value[key])
    entry = DisclosedJavaMaterialEntry(**value)
    verify_disclosed_java_material_entry(entry)
    if dump_disclosed_java_material_entry(entry) != _bytes(raw):
        raise ValueError("disclosed material entry is not canonical")
    return entry


def verify_disclosed_java_material_entry(entry: DisclosedJavaMaterialEntry) -> None:
    body = asdict(entry)
    claimed = body.pop("entry_hash")
    hashes = (
        entry.archive_hash,
        entry.pom_hash,
        entry.source_tree_hash,
        entry.selected_path_manifest_hash,
        entry.correspondence_hash,
        *entry.raw_source_hashes,
        *entry.canonical_source_hashes,
        *entry.declaration_fingerprints,
    )
    if (
        entry.schema_version != DISCLOSED_REGISTRY_SCHEMA_VERSION
        or not entry.coordinate.endswith(f":{entry.version}")
        or not entry.source_url.startswith("https://repo.maven.apache.org/maven2/")
        or any(not _hash(item) for item in hashes)
        or not _commit(entry.scm_revision)
        or tuple(sorted(set(entry.raw_source_hashes))) != entry.raw_source_hashes
        or tuple(sorted(set(entry.canonical_source_hashes)))
        != entry.canonical_source_hashes
        or tuple(sorted(set(entry.selected_relative_paths)))
        != entry.selected_relative_paths
        or tuple(sorted(set(entry.declaration_fingerprints)))
        != entry.declaration_fingerprints
        or content_hash(entry.selected_relative_paths)
        != entry.selected_path_manifest_hash
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid disclosed Java material entry")


def append_disclosed_java_entries(
    root: Path,
    entries: tuple[DisclosedJavaMaterialEntry, ...],
) -> DisclosedJavaRegistryManifest:
    existing = load_disclosed_java_registry(root) if root.exists() else ()
    current_manifest = _load_current_manifest(root) if root.exists() else None
    by_hash = {item.entry_hash: item for item in existing}
    for entry in entries:
        verify_disclosed_java_material_entry(entry)
        by_hash[entry.entry_hash] = entry
    _reject_identity_conflicts(tuple(by_hash.values()))
    entry_hashes = tuple(sorted(by_hash))
    body = {
        "schema_version": DISCLOSED_REGISTRY_SCHEMA_VERSION,
        "previous_manifest_hash": current_manifest.manifest_hash
        if current_manifest
        else None,
        "entry_hashes": entry_hashes,
    }
    manifest = DisclosedJavaRegistryManifest(**body, manifest_hash=content_hash(body))
    root.mkdir(parents=True, exist_ok=True)
    entries_root = root / "entries"
    manifests_root = root / "manifests"
    entries_root.mkdir(exist_ok=True)
    manifests_root.mkdir(exist_ok=True)
    for entry in by_hash.values():
        path = entries_root / f"{entry.entry_hash}.json"
        raw = dump_disclosed_java_material_entry(entry)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("content-addressed disclosure entry was replaced")
        path.write_bytes(raw)
    manifest_raw = _dump_manifest(manifest)
    (manifests_root / f"{manifest.manifest_hash}.json").write_bytes(manifest_raw)
    (root / "registry_manifest.json").write_bytes(manifest_raw)
    verify_disclosed_java_registry(root)
    return manifest


def append_disclosed_java_entries_v2(
    root: Path,
    entries: tuple[DisclosedJavaMaterialEntry, ...],
    *,
    acquisition_run_id: str,
    f20_sha: str,
) -> tuple[DisclosedJavaRegistryManifest, DisclosureRegistryAppendReceipt]:
    """Append a new ordered suffix and bind it to the fresh acquisition."""

    if not root.exists():
        raise ValueError("registry v2 requires an existing disclosed-history root")
    if not entries:
        raise ValueError("registry v2 append cannot be empty")
    if not acquisition_run_id or _GIT_SHA.fullmatch(f20_sha) is None:
        raise ValueError("registry v2 append requires run ID and exact F20")
    verify_disclosed_java_registry(root)
    current = _load_current_manifest(root)
    existing = load_disclosed_java_registry(root)
    new_entries = tuple(entries)
    for entry in new_entries:
        verify_disclosed_java_material_entry(entry)
    appended_hashes = tuple(sorted(item.entry_hash for item in new_entries))
    if len(set(appended_hashes)) != len(appended_hashes):
        raise ValueError("registry v2 append contains a duplicate entry hash")
    if set(appended_hashes) & set(current.entry_hashes):
        raise ValueError("registry v2 append repeats an existing entry hash")
    _reject_identity_conflicts((*existing, *new_entries))
    resulting_hashes = (*current.entry_hashes, *appended_hashes)
    manifest_body = {
        "schema_version": DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION,
        "previous_manifest_hash": current.manifest_hash,
        "entry_hashes": resulting_hashes,
    }
    manifest = DisclosedJavaRegistryManifest(
        **manifest_body, manifest_hash=content_hash(manifest_body)
    )
    entries_root = root / "entries"
    manifests_root = root / "manifests"
    manifest_raw = _dump_manifest(manifest)
    manifest_path = manifests_root / f"{manifest.manifest_hash}.json"
    current_path = root / "registry_manifest.json"
    current_raw = current_path.read_bytes()
    entry_payloads = tuple(
        (
            entries_root / f"{entry.entry_hash}.json",
            dump_disclosed_java_material_entry(entry),
        )
        for entry in new_entries
    )
    if manifest_path.exists():
        raise ValueError("registry v2 manifest path already exists")
    if any(path.exists() for path, _raw in entry_payloads):
        raise ValueError("registry v2 entry path already exists")
    created: list[Path] = []
    current_replaced = False
    try:
        for path, raw in entry_payloads:
            path.write_bytes(raw)
            created.append(path)
        manifest_path.write_bytes(manifest_raw)
        created.append(manifest_path)
        current_path.write_bytes(manifest_raw)
        current_replaced = True
        verify_disclosed_java_registry(root)
    except Exception:
        if current_replaced or current_path.read_bytes() != current_raw:
            current_path.write_bytes(current_raw)
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    receipt_body = {
        "schema_version": DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION,
        "previous_registry_manifest_hash": current.manifest_hash,
        "previous_entry_count": len(current.entry_hashes),
        "appended_entry_hashes": appended_hashes,
        "appended_entry_count": len(appended_hashes),
        "resulting_entry_count": len(resulting_hashes),
        "resulting_manifest_hash": manifest.manifest_hash,
        "acquisition_run_id": acquisition_run_id,
        "f20_sha": f20_sha,
    }
    receipt = DisclosureRegistryAppendReceipt(
        **receipt_body, receipt_hash=content_hash(receipt_body)
    )
    verify_disclosure_registry_append_receipt(receipt, current, manifest)
    return manifest, receipt


def verify_disclosure_registry_append_receipt(
    receipt: DisclosureRegistryAppendReceipt,
    previous: DisclosedJavaRegistryManifest,
    resulting: DisclosedJavaRegistryManifest,
) -> None:
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if (
        receipt.schema_version != DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION
        or receipt.previous_registry_manifest_hash != previous.manifest_hash
        or receipt.previous_entry_count != len(previous.entry_hashes)
        or receipt.appended_entry_count != len(receipt.appended_entry_hashes)
        or receipt.appended_entry_count <= 0
        or tuple(sorted(set(receipt.appended_entry_hashes)))
        != receipt.appended_entry_hashes
        or set(receipt.appended_entry_hashes) & set(previous.entry_hashes)
        or receipt.resulting_entry_count
        != receipt.previous_entry_count + receipt.appended_entry_count
        or receipt.resulting_manifest_hash != resulting.manifest_hash
        or resulting.schema_version != DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION
        or resulting.previous_manifest_hash != previous.manifest_hash
        or resulting.entry_hashes
        != (*previous.entry_hashes, *receipt.appended_entry_hashes)
        or not receipt.acquisition_run_id
        or _GIT_SHA.fullmatch(receipt.f20_sha) is None
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid disclosure registry append receipt")


def load_disclosed_java_registry(
    root: Path = DEFAULT_REGISTRY_ROOT,
) -> tuple[DisclosedJavaMaterialEntry, ...]:
    if not root.exists():
        return ()
    manifest = _load_current_manifest(root)
    return tuple(
        load_disclosed_java_material_entry(
            (root / "entries" / f"{entry_hash}.json").read_bytes()
        )
        for entry_hash in manifest.entry_hashes
    )


def verify_disclosed_java_registry(root: Path = DEFAULT_REGISTRY_ROOT) -> None:
    if not root.exists():
        return
    manifest = _load_current_manifest(root)
    actual = tuple(sorted(path.stem for path in (root / "entries").glob("*.json")))
    if actual != tuple(sorted(manifest.entry_hashes)):
        raise ValueError("disclosed registry is truncated or contains an unknown entry")
    entries = load_disclosed_java_registry(root)
    _reject_identity_conflicts(entries)
    seen = set()
    cursor = manifest
    while True:
        if cursor.manifest_hash in seen:
            raise ValueError("disclosed registry manifest chain contains a cycle")
        seen.add(cursor.manifest_hash)
        snapshot_path = root / "manifests" / f"{cursor.manifest_hash}.json"
        if (
            not snapshot_path.exists()
            or _load_manifest(snapshot_path.read_bytes()) != cursor
        ):
            raise ValueError(
                "disclosed registry manifest snapshot is missing or replaced"
            )
        if cursor.previous_manifest_hash is None:
            break
        previous_path = root / "manifests" / f"{cursor.previous_manifest_hash}.json"
        if not previous_path.exists():
            raise ValueError("disclosed registry manifest history is missing")
        previous = _load_manifest(previous_path.read_bytes())
        if cursor.schema_version == DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION:
            prefix = cursor.entry_hashes[: len(previous.entry_hashes)]
            if prefix != previous.entry_hashes or len(cursor.entry_hashes) <= len(
                previous.entry_hashes
            ):
                raise ValueError(
                    "disclosed registry v2 append history is not an exact prefix"
                )
        elif not set(previous.entry_hashes).issubset(cursor.entry_hashes):
            raise ValueError("disclosed registry rollback or deletion detected")
        cursor = previous
    known_manifests = {path.stem for path in (root / "manifests").glob("*.json")}
    if known_manifests != seen:
        raise ValueError("disclosed registry contains a skipped/orphan manifest parent")


def _load_current_manifest(root):
    path = root / "registry_manifest.json"
    if not path.exists():
        raise ValueError("disclosed registry manifest is missing")
    return _load_manifest(path.read_bytes())


def _load_manifest(raw):
    value = _load_json(raw)
    _fields(
        value,
        {"schema_version", "previous_manifest_hash", "entry_hashes", "manifest_hash"},
        "disclosed registry manifest",
    )
    if not isinstance(value["entry_hashes"], list):
        raise TypeError("registry entry hashes must be an array")
    manifest = DisclosedJavaRegistryManifest(
        schema_version=value["schema_version"],
        previous_manifest_hash=value["previous_manifest_hash"],
        entry_hashes=tuple(value["entry_hashes"]),
        manifest_hash=value["manifest_hash"],
    )
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if (
        manifest.schema_version
        not in {
            DISCLOSED_REGISTRY_SCHEMA_VERSION,
            DISCLOSED_REGISTRY_APPEND_SCHEMA_VERSION,
        }
        or len(set(manifest.entry_hashes)) != len(manifest.entry_hashes)
        or (
            manifest.schema_version == DISCLOSED_REGISTRY_SCHEMA_VERSION
            and tuple(sorted(manifest.entry_hashes)) != manifest.entry_hashes
        )
        or any(not _hash(item) for item in manifest.entry_hashes)
        or (
            manifest.previous_manifest_hash is not None
            and not _hash(manifest.previous_manifest_hash)
        )
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid disclosed registry manifest")
    if _dump_manifest(manifest) != _bytes(raw):
        raise ValueError("disclosed registry manifest is not canonical")
    return manifest


def _dump_manifest(manifest):
    return (canonical_json(asdict(manifest)) + "\n").encode("utf-8")


def _reject_identity_conflicts(entries):
    for field in (
        "coordinate",
        "source_url",
        "archive_hash",
        "source_tree_hash",
        "scm_revision",
        "correspondence_hash",
    ):
        values = {}
        for entry in entries:
            identity = getattr(entry, field)
            # Failed/review acquisitions are still disclosed after their source JAR
            # was downloaded.  An unavailable downstream SCM identity is encoded by
            # the existing all-zero sentinel and is deliberately not an identity.
            if field in {
                "source_tree_hash",
                "scm_revision",
                "correspondence_hash",
            } and set(identity) == {"0"}:
                continue
            prior = values.setdefault(identity, entry.entry_hash)
            if prior != entry.entry_hash:
                raise ValueError(
                    f"duplicate disclosed identity has different content: {field}"
                )


def _load_json(raw):
    try:
        return json.loads(
            _bytes(raw).decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed disclosed registry JSON") from exc


def _bytes(raw):
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {label} field set")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _hash(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= set("0123456789abcdef")
    )


def _commit(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and set(value) <= set("0123456789abcdef")
    )
