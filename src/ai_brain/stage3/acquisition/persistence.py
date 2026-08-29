"""Content-addressed acquisition store with canonical JSON objects."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.models import *
from ai_brain.stage3.knowledge_ir.records import EpistemicCharacter, KnowledgeKind
from ai_brain.stage3.knowledge_ir.serialization import load_content

_HASH = re.compile(r"^[0-9a-f]{64}$")


class AcquisitionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.blob_root = self.root / "blobs"
        self.object_root = self.root / "objects"

    @classmethod
    def open_or_initialize(cls, root: Path):
        value = cls(root)
        value.blob_root.mkdir(parents=True, exist_ok=True)
        value.object_root.mkdir(parents=True, exist_ok=True)
        value.verify()
        return value

    def put_blob(self, data: bytes, *, expected_hash: str | None = None) -> str:
        digest = bytes_hash(data)
        if expected_hash is not None and digest != expected_hash:
            raise ValueError("source blob hash mismatch")
        path = self._blob_path(digest)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("content hash collision simulation detected")
            return digest
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        return digest

    def get_blob(self, digest: str) -> bytes:
        path = self._blob_path(digest)
        data = path.read_bytes()
        if bytes_hash(data) != digest:
            raise ValueError("acquisition blob checksum mismatch")
        return data

    def save_bundle(self, value: SourceBundle) -> Path:
        row = asdict(value)
        return self._save("bundles", content_hash(row), row)

    def load_bundle(self, digest: str) -> SourceBundle:
        row = self._load("bundles", digest)
        documents = tuple(_document(item) for item in row["documents"])
        manifest_row = row["manifest"]
        manifest = AcquisitionManifest(
            **{
                **manifest_row,
                "document_hashes": tuple(manifest_row["document_hashes"]),
            }
        )
        return SourceBundle(
            **{
                **row,
                "domain_tags": tuple(row["domain_tags"]),
                "documents": documents,
                "manifest": manifest,
            }
        )

    def save_segments(self, bundle_hash: str, values: tuple[SourceSegment, ...]) -> str:
        row = {
            "bundle_hash": bundle_hash,
            "segments": [asdict(value) for value in values],
        }
        digest = content_hash(row)
        self._save("segments", digest, row)
        return digest

    def load_segments(self, digest: str) -> tuple[SourceSegment, ...]:
        row = self._load("segments", digest)
        return tuple(_segment(item) for item in row["segments"])

    def save_proposals(
        self, segment_set_hash: str, values: tuple[KnowledgeProposal, ...]
    ) -> str:
        row = {
            "segment_set_hash": segment_set_hash,
            "proposals": [asdict(value) for value in values],
        }
        digest = content_hash(row)
        self._save("proposals", digest, row)
        return digest

    def load_proposals(self, digest: str) -> tuple[KnowledgeProposal, ...]:
        row = self._load("proposals", digest)
        return tuple(_proposal(item) for item in row["proposals"])

    def save_field_evidence(
        self, proposal_set_hash: str, values: tuple[FieldSourceEvidence, ...]
    ) -> str:
        row = {
            "proposal_set_hash": proposal_set_hash,
            "field_evidence": [asdict(value) for value in values],
        }
        digest = content_hash(row)
        self._save("field-evidence", digest, row)
        return digest

    def load_field_evidence(self, digest: str) -> tuple[FieldSourceEvidence, ...]:
        row = self._load("field-evidence", digest)
        return tuple(_field_evidence(item) for item in row["field_evidence"])

    def save_reviews(
        self, proposal_set_hash: str, values: tuple[AcquisitionReview, ...]
    ) -> str:
        row = {
            "proposal_set_hash": proposal_set_hash,
            "reviews": [asdict(value) for value in values],
        }
        digest = content_hash(row)
        self._save("reviews", digest, row)
        return digest

    def verify(self) -> dict[str, object]:
        if not self.root.exists():
            return {"status": "VERIFIED", "blob_count": 0, "object_count": 0}
        blobs = tuple(self.blob_root.rglob("*")) if self.blob_root.exists() else ()
        files = tuple(path for path in blobs if path.is_file())
        for path in files:
            if (
                path.is_symlink()
                or not _HASH.fullmatch(path.name)
                or bytes_hash(path.read_bytes()) != path.name
            ):
                raise ValueError("acquisition blob store is corrupt")
        objects = (
            tuple(self.object_root.rglob("*.json")) if self.object_root.exists() else ()
        )
        for path in objects:
            if path.is_symlink():
                raise ValueError("acquisition object symlink is forbidden")
            row = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
            )
            if content_hash(row) != path.stem:
                raise ValueError("acquisition object hash mismatch")
        return {
            "status": "VERIFIED",
            "blob_count": len(files),
            "object_count": len(objects),
        }

    def backup(self, output: Path) -> dict[str, object]:
        verification = self.verify()
        if output.exists():
            raise FileExistsError("acquisition backup target exists")
        shutil.copytree(self.root, output)
        restored = AcquisitionStore(output)
        return {
            **restored.verify(),
            "status": "BACKED_UP",
            "source_object_count": verification["object_count"],
        }

    @classmethod
    def restore(cls, backup: Path, target: Path):
        if target.exists():
            raise FileExistsError("acquisition restore target exists")
        shutil.copytree(backup, target)
        value = cls(target)
        value.verify()
        return value

    def _blob_path(self, digest: str) -> Path:
        if not _HASH.fullmatch(digest):
            raise ValueError("invalid acquisition blob identity")
        return self.blob_root / digest[:2] / digest

    def _save(self, kind: str, digest: str, value) -> Path:
        if not _HASH.fullmatch(digest) or content_hash(value) != digest:
            raise ValueError("acquisition object identity mismatch")
        path = self.object_root / kind / f"{digest}.json"
        text = canonical_json(value) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise ValueError("acquisition object collision")
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def _load(self, kind: str, digest: str):
        if not _HASH.fullmatch(digest):
            raise ValueError("invalid acquisition object identity")
        row = json.loads(
            (self.object_root / kind / f"{digest}.json").read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
        if content_hash(row) != digest:
            raise ValueError("acquisition object checksum mismatch")
        return row


def _document(row) -> SourceDocument:
    structure = DocumentStructure(**row["structure"])
    return SourceDocument(
        **{
            **row,
            "media_type": SourceMediaType(row["media_type"]),
            "source_metadata": tuple(tuple(item) for item in row["source_metadata"]),
            "structure": structure,
        }
    )


def _segment(row) -> SourceSegment:
    location = SourceLocation(
        **{
            **row["source_location"],
            "heading_path": tuple(row["source_location"]["heading_path"]),
        }
    )
    return SourceSegment(
        **{**row, "kind": SegmentKind(row["kind"]), "source_location": location}
    )


def _proposal(row) -> KnowledgeProposal:
    kind = KnowledgeKind(row["proposed_kind"])
    return KnowledgeProposal(
        **{
            **row,
            "segment_ids": tuple(row["segment_ids"]),
            "proposed_kind": kind,
            "proposed_epistemic_character": EpistemicCharacter(
                row["proposed_epistemic_character"]
            ),
            "proposed_content": load_content(kind, row["proposed_content"]),
            "proposed_dependencies": tuple(row["proposed_dependencies"]),
            "proposed_applicability": tuple(row["proposed_applicability"]),
            "proposed_capabilities": tuple(row["proposed_capabilities"]),
            "extraction_method": ExtractionMethod(row["extraction_method"]),
            "status": ProposalStatus(row["status"]),
            "ambiguity_fields": tuple(row["ambiguity_fields"]),
        }
    )


def _field_evidence(row) -> FieldSourceEvidence:
    return FieldSourceEvidence(
        **{
            **row,
            "heading_path": tuple(row["heading_path"]),
            "extraction_method": ExtractionMethod(row["extraction_method"]),
        }
    )


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in acquisition store")
        result[key] = value
    return result
