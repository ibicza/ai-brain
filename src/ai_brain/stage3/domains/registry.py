"""Transactional checksummed installed-domain registry."""

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
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityResolutionReceipt,
)
from ai_brain.stage3.domains.approval import (
    DomainPackApprovalEnvelope,
    PackApprovalDecision,
    verify_approval,
)
from ai_brain.stage3.domains.pack import DomainPack
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import (
    CAPABILITY_RESOLUTION_SCHEMA_VERSION,
    DOMAIN_REGISTRY_SCHEMA_VERSION,
)


class InstalledDomainStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True)
class InstalledDomain:
    domain_id: str
    pack_version: str
    pack_hash: str
    approval_hash: str
    capability_resolution_receipt_hashes: tuple[str, ...]
    status: InstalledDomainStatus
    pack_root: str
    installed_at: str
    installation_receipt_hash: str


class InstalledDomainRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.database_path = self.root / "installed_domains.sqlite3"

    @classmethod
    def initialize(
        cls, root: Path, *, created_at: str | None = None
    ) -> InstalledDomainRegistry:
        value = cls(root)
        value.root.mkdir(parents=True, exist_ok=True)
        if value.database_path.exists():
            raise FileExistsError("installed-domain registry exists")
        with value._connection() as connection:
            connection.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE domains(domain_id TEXT NOT NULL,pack_version TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,PRIMARY KEY(domain_id,pack_version));
            CREATE TABLE approvals(approval_hash TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT NOT NULL);
            CREATE TABLE resolutions(receipt_hash TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT NOT NULL);
            CREATE TABLE audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,payload_hash TEXT NOT NULL,created_at TEXT NOT NULL);
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
    def open_or_initialize(cls, root: Path) -> InstalledDomainRegistry:
        return (
            cls.open(root)
            if (root.resolve() / "installed_domains.sqlite3").exists()
            else cls.initialize(root)
        )

    @classmethod
    def open(cls, root: Path) -> InstalledDomainRegistry:
        value = cls(root)
        if not value.database_path.is_file():
            raise FileNotFoundError("installed-domain registry is missing")
        with value._connection() as c:
            row = c.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
        if row is None or row[0] != str(DOMAIN_REGISTRY_SCHEMA_VERSION):
            raise ValueError("domain registry schema mismatch")
        value.verify()
        return value

    def install(
        self,
        pack: DomainPack,
        approval: DomainPackApprovalEnvelope,
        resolutions: tuple[CapabilityResolutionReceipt, ...],
        *,
        installed_at: str | None = None,
    ) -> InstalledDomain:
        validate_pack(pack)
        verify_approval(approval)
        if (
            approval.decision is not PackApprovalDecision.APPROVE
            or approval.pack_hash != pack.manifest.pack_content_hash
        ):
            raise ValueError("pack lacks exact explicit approval")
        receipt_hashes = tuple(x.receipt_hash for x in resolutions)
        if approval.capability_resolution_receipt_hashes != receipt_hashes:
            raise ValueError(
                "approval does not bind the complete capability resolution set"
            )
        required = {x.capability_id for x in pack.manifest.required_capabilities}
        if {x.required_capability_id for x in resolutions} != required:
            raise ValueError("installed pack has incomplete capability resolutions")
        pack_path = Path(pack.root)
        try:
            stored_pack_root = pack_path.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            stored_pack_root = str(pack_path)
        body = {
            "domain_id": pack.manifest.domain_id,
            "pack_version": pack.manifest.pack_version,
            "pack_hash": pack.manifest.pack_content_hash,
            "approval_hash": approval.approval_hash,
            "capability_resolution_receipt_hashes": receipt_hashes,
            "status": InstalledDomainStatus.ACTIVE,
            "pack_root": stored_pack_root,
            "installed_at": installed_at or utc_now(),
        }
        item = InstalledDomain(**body, installation_receipt_hash=content_hash(body))
        payload = canonical_json(asdict(item))
        approval_payload = canonical_json(asdict(approval))
        with self._connection() as c:
            if c.execute(
                "SELECT 1 FROM domains WHERE domain_id=? AND pack_version=?",
                (item.domain_id, item.pack_version),
            ).fetchone():
                raise ValueError("domain pack is already installed")
            c.execute(
                "INSERT INTO approvals VALUES(?,?,?)",
                (
                    approval.approval_hash,
                    approval_payload,
                    bytes_hash(approval_payload.encode()),
                ),
            )
            for receipt in resolutions:
                text = canonical_json(asdict(receipt))
                c.execute(
                    "INSERT INTO resolutions VALUES(?,?,?)",
                    (receipt.receipt_hash, text, bytes_hash(text.encode())),
                )
            c.execute(
                "INSERT INTO domains VALUES(?,?,?,?)",
                (
                    item.domain_id,
                    item.pack_version,
                    payload,
                    bytes_hash(payload.encode()),
                ),
            )
            c.execute(
                "INSERT INTO audit(kind,payload_hash,created_at) VALUES(?,?,?)",
                ("INSTALLED", item.installation_receipt_hash, item.installed_at),
            )
        return item

    def list(self) -> tuple[InstalledDomain, ...]:
        with self._connection() as c:
            rows = c.execute(
                "SELECT payload,payload_hash FROM domains ORDER BY domain_id,pack_version"
            ).fetchall()
        result = []
        for payload, digest in rows:
            if bytes_hash(payload.encode()) != digest:
                raise ValueError("installed-domain checksum mismatch")
            row = json.loads(payload)
            row["capability_resolution_receipt_hashes"] = tuple(
                row["capability_resolution_receipt_hashes"]
            )
            row["status"] = InstalledDomainStatus(row["status"])
            item = InstalledDomain(**row)
            body = asdict(item)
            expected = body.pop("installation_receipt_hash")
            if content_hash(body) != expected:
                raise ValueError("installation receipt hash mismatch")
            result.append(item)
        return tuple(result)

    def show(self, domain_id: str, pack_version: str | None = None) -> InstalledDomain:
        matches = [
            x
            for x in self.list()
            if x.domain_id == domain_id
            and (pack_version is None or x.pack_version == pack_version)
        ]
        if not matches:
            raise KeyError(domain_id)
        return matches[-1]

    def deprecate(self, domain_id: str, pack_version: str) -> InstalledDomain:
        return self._status(domain_id, pack_version, InstalledDomainStatus.DEPRECATED)

    def uninstall(self, domain_id: str, pack_version: str) -> dict[str, str]:
        item = self.show(domain_id, pack_version)
        with self._connection() as c:
            c.execute(
                "DELETE FROM domains WHERE domain_id=? AND pack_version=?",
                (domain_id, pack_version),
            )
            c.execute(
                "INSERT INTO audit(kind,payload_hash,created_at) VALUES(?,?,?)",
                ("UNINSTALLED", item.installation_receipt_hash, utc_now()),
            )
        return {
            "status": "UNINSTALLED",
            "history_status": "HISTORY_VALID_BUT_PACK_UNAVAILABLE",
            "domain_id": domain_id,
            "pack_version": pack_version,
        }

    def _status(self, domain_id, pack_version, status):
        old = self.show(domain_id, pack_version)
        body = asdict(old)
        body["status"] = status
        body.pop("installation_receipt_hash")
        new = InstalledDomain(**body, installation_receipt_hash=content_hash(body))
        payload = canonical_json(asdict(new))
        with self._connection() as c:
            c.execute(
                "UPDATE domains SET payload=?,payload_hash=? WHERE domain_id=? AND pack_version=?",
                (payload, bytes_hash(payload.encode()), domain_id, pack_version),
            )
        return new

    def verify(self) -> dict[str, object]:
        with self._connection() as c:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("domain registry SQLite integrity failed")
            approval_rows = c.execute(
                "SELECT approval_hash,payload,payload_hash FROM approvals"
            ).fetchall()
            receipt_rows = c.execute(
                "SELECT receipt_hash,payload,payload_hash FROM resolutions"
            ).fetchall()
        approvals = set()
        for identity, payload, checksum in approval_rows:
            if bytes_hash(payload.encode()) != checksum:
                raise ValueError("installed-domain approval checksum mismatch")
            row = json.loads(payload)
            row["reviewer_type"] = ActorIdentityType(row["reviewer_type"])
            row["decision"] = PackApprovalDecision(row["decision"])
            row["source_binding_hashes"] = tuple(row["source_binding_hashes"])
            row["capability_resolution_receipt_hashes"] = tuple(
                row["capability_resolution_receipt_hashes"]
            )
            approval = DomainPackApprovalEnvelope(**row)
            verify_approval(approval)
            if approval.approval_hash != identity:
                raise ValueError("installed-domain approval identity mismatch")
            approvals.add(identity)
        receipts = set()
        for identity, payload, checksum in receipt_rows:
            if bytes_hash(payload.encode()) != checksum:
                raise ValueError("installed-domain resolution checksum mismatch")
            row = json.loads(payload)
            row["dependency_capabilities"] = tuple(row["dependency_capabilities"])
            row["authority_class"] = AuthorityClass(row["authority_class"])
            receipt = CapabilityResolutionReceipt(**row)
            body = asdict(receipt)
            digest = body.pop("receipt_hash")
            if (
                receipt.schema_version != CAPABILITY_RESOLUTION_SCHEMA_VERSION
                or content_hash(body) != digest
                or digest != identity
            ):
                raise ValueError("installed-domain resolution receipt mismatch")
            receipts.add(identity)
        items = self.list()
        for item in items:
            if (
                item.approval_hash not in approvals
                or not set(item.capability_resolution_receipt_hashes) <= receipts
            ):
                raise ValueError("installed domain authority closure is incomplete")
        return {
            "status": "VERIFIED",
            "installed_count": len(items),
            "registry_hash": content_hash(tuple(asdict(x) for x in items)),
        }

    def export(self, output: Path) -> dict[str, object]:
        result = {
            "schema_version": DOMAIN_REGISTRY_SCHEMA_VERSION,
            "domains": [asdict(x) for x in self.list()],
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
        verification = self.verify()
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source, closing(sqlite3.connect(output)) as target:
            source.backup(target)
        return {
            **verification,
            "status": "BACKED_UP",
            "bytes_hash": bytes_hash(output.read_bytes()),
        }

    @classmethod
    def restore(cls, backup: Path, target_root: Path) -> InstalledDomainRegistry:
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / "installed_domains.sqlite3"
        if target.exists():
            raise FileExistsError("domain registry restore target exists")
        shutil.copyfile(backup, target)
        return cls.open(target_root)

    @contextmanager
    def _connection(self):
        c = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=5000")
            with c:
                yield c
        finally:
            c.close()
