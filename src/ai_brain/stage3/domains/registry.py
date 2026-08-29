"""Content-addressed installed-domain registry v2."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)
from ai_brain.stage3.acquisition.evaluation import verify_pack_evaluation
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityResolutionReceipt,
)
from ai_brain.stage3.capabilities.resolution import verify_resolution
from ai_brain.stage3.domains.approval import (
    DomainPackApprovalEnvelope,
    PackApprovalDecision,
    verify_approval,
)
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.pack import DomainPack
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import (
    CAPABILITY_RESOLUTION_SCHEMA_VERSION,
    DOMAIN_REGISTRY_SCHEMA_VERSION,
    UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
)


class InstalledDomainStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True)
class InstalledDomain:
    domain_id: str
    pack_version: str
    pack_hash: str
    stored_pack_bytes_hash: str
    approval_hash: str
    capability_resolution_receipt_hashes: tuple[str, ...]
    capability_registry_hash: str
    provider_registry_hash: str
    validation_result_hash: str
    evaluation_result_hash: str
    dependency_pack_hashes: tuple[str, ...]
    status: InstalledDomainStatus
    pack_root: str
    installed_at: str
    installation_receipt_hash: str


class InstalledDomainRegistry:
    def __init__(
        self, root: Path, *, capability_registry=None, provider_registry=None
    ) -> None:
        self.root = root.resolve()
        self.database_path = self.root / "installed_domains.sqlite3"
        self.pack_store = self.root / "packs"
        self.capability_registry = capability_registry
        self.provider_registry = provider_registry

    @classmethod
    def initialize(
        cls,
        root: Path,
        *,
        capability_registry=None,
        provider_registry=None,
        created_at: str | None = None,
    ):
        value = cls(
            root,
            capability_registry=capability_registry,
            provider_registry=provider_registry,
        )
        value.root.mkdir(parents=True, exist_ok=True)
        value.pack_store.mkdir(parents=True, exist_ok=True)
        if value.database_path.exists():
            raise FileExistsError("installed-domain registry exists")
        with value._connection() as connection:
            connection.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE domains(domain_id TEXT NOT NULL,pack_version TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,PRIMARY KEY(domain_id,pack_version));
            CREATE TABLE approvals(approval_hash TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT NOT NULL);
            CREATE TABLE resolutions(receipt_hash TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT NOT NULL);
            CREATE TABLE audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,payload TEXT NOT NULL,event_hash TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            connection.executemany(
                "INSERT INTO metadata VALUES(?,?)",
                (
                    ("schema_version", str(DOMAIN_REGISTRY_SCHEMA_VERSION)),
                    ("created_at", created_at or utc_now()),
                ),
            )
        return value

    @classmethod
    def open_or_initialize(
        cls, root: Path, *, capability_registry=None, provider_registry=None
    ):
        return (
            cls.open(
                root,
                capability_registry=capability_registry,
                provider_registry=provider_registry,
            )
            if (root.resolve() / "installed_domains.sqlite3").exists()
            else cls.initialize(
                root,
                capability_registry=capability_registry,
                provider_registry=provider_registry,
            )
        )

    @classmethod
    def open(cls, root: Path, *, capability_registry=None, provider_registry=None):
        value = cls(
            root,
            capability_registry=capability_registry,
            provider_registry=provider_registry,
        )
        if not value.database_path.is_file():
            raise FileNotFoundError("installed-domain registry is missing")
        with value._connection() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
        if row is None or row[0] != str(DOMAIN_REGISTRY_SCHEMA_VERSION):
            raise ValueError("domain registry schema mismatch")
        value.verify(
            require_current_authority=capability_registry is not None
            or provider_registry is not None
        )
        return value

    def install(
        self,
        pack: DomainPack,
        approval: DomainPackApprovalEnvelope,
        resolutions: tuple[CapabilityResolutionReceipt, ...],
        *,
        capability_registry=None,
        provider_registry=None,
        installed_at: str | None = None,
    ) -> InstalledDomain:
        capability_registry = capability_registry or self.capability_registry
        provider_registry = provider_registry or self.provider_registry
        if capability_registry is None or provider_registry is None:
            raise ValueError(
                "domain installation requires current provider and capability registries"
            )
        validation = validate_pack(pack)
        verify_approval(approval)
        if (
            approval.decision is not PackApprovalDecision.APPROVE
            or approval.pack_hash != pack.manifest.pack_content_hash
        ):
            raise ValueError("pack lacks exact explicit approval")
        if (
            approval.knowledge_ir_schema != UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
            or approval.concept_graph_hash != pack.manifest.concept_graph_hash
            or approval.source_binding_hashes != pack.manifest.source_binding_hashes
            or approval.evaluation_manifest_hash
            != pack.manifest.evaluation_manifest_hash
            or approval.validation_report_hash != content_hash(validation)
        ):
            raise ValueError("approval fields do not match the exact pack")
        if len({item.receipt_hash for item in resolutions}) != len(resolutions):
            raise ValueError("duplicate capability resolution receipt")
        receipt_hashes = tuple(item.receipt_hash for item in resolutions)
        if approval.capability_resolution_receipt_hashes != receipt_hashes:
            raise ValueError(
                "approval does not bind the complete capability resolution set"
            )
        roots = {item.capability_id for item in pack.manifest.required_capabilities}
        if not roots <= {item.required_capability_id for item in resolutions}:
            raise ValueError(
                "installed pack has incomplete root capability resolutions"
            )
        for receipt in resolutions:
            verify_resolution(
                receipt, capability_registry, provider_registry, resolutions
            )
        evaluation = verify_pack_evaluation(pack)
        if evaluation["status"] != "PASS":
            raise ValueError("pack evaluation failed")
        dependencies = self._dependency_items(pack)
        self._verify_dependency_cycle(pack, dependencies)
        self._verify_cross_pack_targets(pack, dependencies)
        pack_bytes_hash = _pack_bytes_hash(Path(pack.root))
        stored_root = self.pack_store / pack_bytes_hash
        if stored_root.exists():
            if _pack_bytes_hash(stored_root) != pack_bytes_hash:
                raise ValueError("content-addressed pack collision")
        else:
            shutil.copytree(pack.root, stored_root)
        stored_pack = load_pack(stored_root)
        if (
            stored_pack.manifest.pack_content_hash != pack.manifest.pack_content_hash
            or _pack_bytes_hash(stored_root) != pack_bytes_hash
        ):
            raise ValueError("stored pack bytes differ from approved pack")
        stamp = installed_at or utc_now()
        body = {
            "domain_id": pack.manifest.domain_id,
            "pack_version": pack.manifest.pack_version,
            "pack_hash": pack.manifest.pack_content_hash,
            "stored_pack_bytes_hash": pack_bytes_hash,
            "approval_hash": approval.approval_hash,
            "capability_resolution_receipt_hashes": receipt_hashes,
            "capability_registry_hash": capability_registry.registry_hash,
            "provider_registry_hash": provider_registry.registry_hash,
            "validation_result_hash": content_hash(validation),
            "evaluation_result_hash": evaluation["evaluation_result_hash"],
            "dependency_pack_hashes": tuple(item.pack_hash for item in dependencies),
            "status": InstalledDomainStatus.ACTIVE,
            "pack_root": f"packs/{pack_bytes_hash}",
            "installed_at": stamp,
        }
        item = InstalledDomain(**body, installation_receipt_hash=content_hash(body))
        with self._connection() as connection:
            if connection.execute(
                "SELECT 1 FROM domains WHERE domain_id=? AND pack_version=?",
                (item.domain_id, item.pack_version),
            ).fetchone():
                raise ValueError("domain pack is already installed")
            _insert_authority(
                connection,
                "approvals",
                "approval_hash",
                approval.approval_hash,
                asdict(approval),
            )
            for receipt in resolutions:
                _insert_authority(
                    connection,
                    "resolutions",
                    "receipt_hash",
                    receipt.receipt_hash,
                    asdict(receipt),
                )
            payload = canonical_json(asdict(item))
            connection.execute(
                "INSERT INTO domains VALUES(?,?,?,?)",
                (
                    item.domain_id,
                    item.pack_version,
                    payload,
                    bytes_hash(payload.encode()),
                ),
            )
            self._audit(
                connection,
                "INSTALLED",
                {
                    "installation_receipt_hash": item.installation_receipt_hash,
                    "stored_pack_bytes_hash": pack_bytes_hash,
                    "validation_result_hash": item.validation_result_hash,
                    "evaluation_result_hash": item.evaluation_result_hash,
                },
                stamp,
            )
        self.capability_registry, self.provider_registry = (
            capability_registry,
            provider_registry,
        )
        return item

    def list(self) -> tuple[InstalledDomain, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload,payload_hash FROM domains ORDER BY domain_id,pack_version"
            ).fetchall()
        return tuple(_installed(payload, digest) for payload, digest in rows)

    def show(self, domain_id: str, pack_version: str | None = None) -> InstalledDomain:
        matches = [
            item
            for item in self.list()
            if item.domain_id == domain_id
            and (pack_version is None or item.pack_version == pack_version)
        ]
        if not matches:
            raise KeyError(domain_id)
        return matches[-1]

    def load_installed_pack(
        self, domain_id: str, pack_version: str | None = None
    ) -> DomainPack:
        item = self.show(domain_id, pack_version)
        root = (self.root / item.pack_root).resolve()
        if _pack_bytes_hash(root) != item.stored_pack_bytes_hash:
            raise ValueError("installed pack bytes are stale")
        pack = load_pack(root)
        if pack.manifest.pack_content_hash != item.pack_hash:
            raise ValueError("installed pack semantic hash is stale")
        return pack

    def deprecate(self, domain_id: str, pack_version: str) -> InstalledDomain:
        return self._status(domain_id, pack_version, InstalledDomainStatus.DEPRECATED)

    def uninstall(self, domain_id: str, pack_version: str) -> dict[str, str]:
        item = self.show(domain_id, pack_version)
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM domains WHERE domain_id=? AND pack_version=?",
                (domain_id, pack_version),
            )
            self._audit(
                connection,
                "UNINSTALLED",
                {"installation_receipt_hash": item.installation_receipt_hash},
                utc_now(),
            )
        return {
            "status": "UNINSTALLED",
            "history_status": "HISTORY_VALID_BUT_PACK_UNAVAILABLE",
            "domain_id": domain_id,
            "pack_version": pack_version,
        }

    def verify(self, *, require_current_authority: bool = True) -> dict[str, object]:
        with self._connection() as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("domain registry SQLite integrity failed")
            approval_rows = connection.execute(
                "SELECT approval_hash,payload,payload_hash FROM approvals"
            ).fetchall()
            receipt_rows = connection.execute(
                "SELECT receipt_hash,payload,payload_hash FROM resolutions"
            ).fetchall()
            audit_rows = connection.execute(
                "SELECT kind,payload,event_hash,created_at FROM audit ORDER BY sequence"
            ).fetchall()
        approvals = {
            _approval(identity, payload, checksum).approval_hash
            for identity, payload, checksum in approval_rows
        }
        receipts = tuple(
            _receipt(identity, payload, checksum)
            for identity, payload, checksum in receipt_rows
        )
        receipt_hashes = {item.receipt_hash for item in receipts}
        if require_current_authority and (
            self.capability_registry is None or self.provider_registry is None
        ):
            raise ValueError(
                "current authority registries are required for full verification"
            )
        items = self.list()
        for item in items:
            if (
                item.approval_hash not in approvals
                or not set(item.capability_resolution_receipt_hashes) <= receipt_hashes
            ):
                raise ValueError("installed domain authority closure is incomplete")
            pack = self.load_installed_pack(item.domain_id, item.pack_version)
            validation = validate_pack(pack)
            evaluation = verify_pack_evaluation(pack)
            if (
                content_hash(validation) != item.validation_result_hash
                or evaluation["evaluation_result_hash"] != item.evaluation_result_hash
            ):
                raise ValueError("installed validation or evaluation result changed")
            if require_current_authority:
                if (
                    item.capability_registry_hash
                    != self.capability_registry.registry_hash
                    or item.provider_registry_hash
                    != self.provider_registry.registry_hash
                ):
                    raise ValueError("installed authority registry changed")
                closure = tuple(
                    receipt
                    for receipt in receipts
                    if receipt.receipt_hash in item.capability_resolution_receipt_hashes
                )
                for receipt in closure:
                    verify_resolution(
                        receipt,
                        self.capability_registry,
                        self.provider_registry,
                        closure,
                    )
            for dependency_hash in item.dependency_pack_hashes:
                if not any(
                    candidate.pack_hash == dependency_hash
                    and candidate.status is InstalledDomainStatus.ACTIVE
                    for candidate in items
                ):
                    raise ValueError("installed dependency pack is unavailable")
        previous = None
        for kind, payload, event_hash, created_at in audit_rows:
            row = json.loads(payload)
            if event_hash != content_hash(
                {
                    "kind": kind,
                    "payload": row,
                    "previous_event_hash": previous,
                    "created_at": created_at,
                }
            ):
                raise ValueError("domain registry audit chain mismatch")
            previous = event_hash
        return {
            "status": "VERIFIED",
            "installed_count": len(items),
            "registry_hash": content_hash(tuple(asdict(item) for item in items)),
            "audit_event_count": len(audit_rows),
        }

    def verify_currentness(
        self, domain_id: str, pack_version: str | None = None
    ) -> dict[str, object]:
        item = self.show(domain_id, pack_version)
        verification = self.verify(require_current_authority=True)
        return {
            **verification,
            "status": "CURRENT"
            if item.status is InstalledDomainStatus.ACTIVE
            else "STALE",
            "current": item.status is InstalledDomainStatus.ACTIVE,
            "pack_hash": item.pack_hash,
            "stored_pack_bytes_hash": item.stored_pack_bytes_hash,
        }

    def export(self, output: Path) -> dict[str, object]:
        result = {
            "schema_version": DOMAIN_REGISTRY_SCHEMA_VERSION,
            "domains": [asdict(item) for item in self.list()],
        }
        text = canonical_json(result) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline="\n")
        return {
            "status": "EXPORTED",
            "bytes_hash": bytes_hash(text.encode()),
            "installed_count": len(result["domains"]),
        }

    def backup(self, output: Path) -> dict[str, object]:
        verification = self.verify(
            require_current_authority=self.capability_registry is not None
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source, closing(sqlite3.connect(output)) as target:
            source.backup(target)
        sidecar = output.with_suffix(output.suffix + ".packs")
        if sidecar.exists():
            raise FileExistsError("domain registry pack backup target exists")
        shutil.copytree(self.pack_store, sidecar)
        return {
            **verification,
            "status": "BACKED_UP",
            "bytes_hash": bytes_hash(output.read_bytes()),
            "pack_store_hash": _pack_bytes_hash(sidecar),
        }

    @classmethod
    def restore(
        cls,
        backup: Path,
        target_root: Path,
        *,
        capability_registry=None,
        provider_registry=None,
    ):
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / "installed_domains.sqlite3"
        if target.exists():
            raise FileExistsError("domain registry restore target exists")
        shutil.copyfile(backup, target)
        sidecar = backup.with_suffix(backup.suffix + ".packs")
        if not sidecar.is_dir():
            raise FileNotFoundError("domain registry pack backup is missing")
        shutil.copytree(sidecar, target_root / "packs")
        return cls.open(
            target_root,
            capability_registry=capability_registry,
            provider_registry=provider_registry,
        )

    def _dependency_items(self, pack: DomainPack) -> tuple[InstalledDomain, ...]:
        result = []
        for reference in pack.manifest.dependency_packs:
            domain, separator, version = reference.partition("@")
            item = self.show(domain, version if separator else None)
            if item.status is not InstalledDomainStatus.ACTIVE:
                raise ValueError("pack dependency is not active")
            result.append(item)
        return tuple(result)

    def _verify_dependency_cycle(self, pack, dependencies):
        edges = {
            item.domain_id: tuple(
                self.load_installed_pack(
                    item.domain_id, item.pack_version
                ).manifest.dependency_packs
            )
            for item in self.list()
        }
        edges[pack.manifest.domain_id] = tuple(item.domain_id for item in dependencies)
        visiting, done = set(), set()

        def visit(node):
            if node in visiting:
                raise ValueError("pack dependency cycle")
            if node in done:
                return
            visiting.add(node)
            for child in edges.get(node, ()):
                visit(child.partition("@")[0])
            visiting.remove(node)
            done.add(node)

        for node in edges:
            visit(node)

    def _verify_cross_pack_targets(self, pack, dependencies):
        targets = set()
        for item in dependencies:
            dependency = self.load_installed_pack(item.domain_id, item.pack_version)
            targets |= {record.knowledge_id for record in dependency.knowledge_records}
            targets |= {node.concept_id for node in dependency.concept_graph.nodes}
        for edge in pack.concept_graph.edges:
            if (
                edge.dependency_pack is not None
                and edge.target_concept_id not in targets
            ):
                raise ValueError("cross-pack target does not exist")

    def _status(self, domain_id, pack_version, status):
        old = self.show(domain_id, pack_version)
        body = {**asdict(old), "status": status}
        body.pop("installation_receipt_hash")
        new = InstalledDomain(**body, installation_receipt_hash=content_hash(body))
        payload = canonical_json(asdict(new))
        with self._connection() as connection:
            connection.execute(
                "UPDATE domains SET payload=?,payload_hash=? WHERE domain_id=? AND pack_version=?",
                (payload, bytes_hash(payload.encode()), domain_id, pack_version),
            )
            self._audit(
                connection,
                status.value,
                {"installation_receipt_hash": new.installation_receipt_hash},
                utc_now(),
            )
        return new

    def _audit(self, connection, kind, payload, created_at):
        previous = connection.execute(
            "SELECT event_hash FROM audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous[0] if previous else None
        event_hash = content_hash(
            {
                "kind": kind,
                "payload": payload,
                "previous_event_hash": previous_hash,
                "created_at": created_at,
            }
        )
        connection.execute(
            "INSERT INTO audit(kind,payload,event_hash,created_at) VALUES(?,?,?,?)",
            (kind, canonical_json(payload), event_hash, created_at),
        )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            with connection:
                yield connection
        finally:
            connection.close()


def _pack_bytes_hash(root: Path) -> str:
    if not root.is_dir():
        raise FileNotFoundError("pack byte root is missing")
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("pack store contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("pack store contains a non-file entry")
        rows.append((path.relative_to(root).as_posix(), bytes_hash(path.read_bytes())))
    return content_hash(tuple(rows))


def _insert_authority(connection, table, identity_column, identity, value):
    payload = canonical_json(value)
    connection.execute(
        f"INSERT INTO {table}({identity_column},payload,payload_hash) VALUES(?,?,?)",
        (identity, payload, bytes_hash(payload.encode())),
    )


def _installed(payload, digest):
    if bytes_hash(payload.encode()) != digest:
        raise ValueError("installed-domain checksum mismatch")
    row = json.loads(payload)
    for key in ("capability_resolution_receipt_hashes", "dependency_pack_hashes"):
        row[key] = tuple(row[key])
    row["status"] = InstalledDomainStatus(row["status"])
    item = InstalledDomain(**row)
    body = asdict(item)
    expected = body.pop("installation_receipt_hash")
    if content_hash(body) != expected:
        raise ValueError("installation receipt hash mismatch")
    return item


def _approval(identity, payload, checksum):
    if bytes_hash(payload.encode()) != checksum:
        raise ValueError("installed-domain approval checksum mismatch")
    row = json.loads(payload)
    row["reviewer_type"] = ActorIdentityType(row["reviewer_type"])
    row["decision"] = PackApprovalDecision(row["decision"])
    row["source_binding_hashes"] = tuple(row["source_binding_hashes"])
    row["capability_resolution_receipt_hashes"] = tuple(
        row["capability_resolution_receipt_hashes"]
    )
    value = DomainPackApprovalEnvelope(**row)
    verify_approval(value)
    if value.approval_hash != identity:
        raise ValueError("installed-domain approval identity mismatch")
    return value


def _receipt(identity, payload, checksum):
    if bytes_hash(payload.encode()) != checksum:
        raise ValueError("installed-domain resolution checksum mismatch")
    row = json.loads(payload)
    row["dependency_capabilities"] = tuple(row["dependency_capabilities"])
    row["dependency_receipt_hashes"] = tuple(row["dependency_receipt_hashes"])
    row["authority_class"] = AuthorityClass(row["authority_class"])
    value = CapabilityResolutionReceipt(**row)
    body = asdict(value)
    digest = body.pop("receipt_hash")
    if (
        value.schema_version != CAPABILITY_RESOLUTION_SCHEMA_VERSION
        or content_hash(body) != digest
        or digest != identity
    ):
        raise ValueError("installed-domain resolution receipt mismatch")
    return value
