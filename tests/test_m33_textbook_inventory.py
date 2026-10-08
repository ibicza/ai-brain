"""Inventory contract tests; mock readers, not authored textbook PDFs."""

import hashlib
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "textbook_inventory",
    Path(__file__).parents[1] / "scripts/m33_textbook_inventory.py",
)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class Page:
    mediabox = SimpleNamespace(width=100, height=200)

    def extract_text(self):
        return "example"

    def get(self, key):
        return None


def reader(page=None, encrypted=False):
    return SimpleNamespace(pages=[page or Page()], metadata={}, is_encrypted=encrypted)


def test_identity_and_non_admission(tmp_path, monkeypatch):
    source = tmp_path / "mock.pdf"
    source.write_bytes(b"mock-reader-input-not-a-real-pdf")
    monkeypatch.setattr(inventory, "PdfReader", lambda _: reader())
    before = source.read_bytes()
    manifest = inventory.build_manifest(tmp_path)
    book = manifest["books"][0]
    assert book["sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
    assert manifest["schema"] == 2
    assert manifest["total_pdf_pages"] == 1
    assert manifest["training_admitted"] is False
    assert manifest["public_pdf_release_approved"] is False
    assert book["text_layer"]["parser_warning_count"] == 0


def test_warning_is_not_silent_and_logging_restored(tmp_path, monkeypatch):
    class WarningPage(Page):
        def extract_text(self):
            logging.getLogger("pypdf.test").warning("partial extraction")
            return "partial"

    source = tmp_path / "mock.pdf"
    source.write_bytes(b"mock")
    monkeypatch.setattr(inventory, "PdfReader", lambda _: reader(WarningPage()))
    logger = logging.getLogger("pypdf")
    previous = logger.propagate
    layer = inventory.inspect_pdf(source)["text_layer"]
    assert layer["parser_warning_count"] == 1
    assert layer["pdf_pages_with_parser_warnings"] == [1]
    assert layer["quality_status"] == "PARSER_WARNINGS_REVIEW_REQUIRED"
    assert logger.propagate == previous


def test_source_mutation_rejected(tmp_path, monkeypatch):
    source = tmp_path / "mock.pdf"
    source.write_bytes(b"before")

    class MutatingPage(Page):
        def extract_text(self):
            source.write_bytes(b"after")
            return "text"

    monkeypatch.setattr(inventory, "PdfReader", lambda _: reader(MutatingPage()))
    with pytest.raises(ValueError, match="source changed"):
        inventory.inspect_pdf(source)


def test_encrypted_and_empty_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="no PDF"):
        inventory.build_manifest(tmp_path)
    source = tmp_path / "mock.pdf"
    source.write_bytes(b"mock")
    monkeypatch.setattr(inventory, "PdfReader", lambda _: reader(encrypted=True))
    with pytest.raises(ValueError, match="encrypted"):
        inventory.inspect_pdf(source)


def test_duplicates_rejected(tmp_path, monkeypatch):
    for name in ("one.pdf", "two.pdf"):
        (tmp_path / name).write_bytes(b"same mock input")
    monkeypatch.setattr(inventory, "PdfReader", lambda _: reader())
    with pytest.raises(ValueError, match="byte-identical duplicate"):
        inventory.build_manifest(tmp_path)
