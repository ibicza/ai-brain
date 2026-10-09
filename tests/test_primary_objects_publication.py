"""Measured catalogue changes retain old links across Excel length boundaries."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from m33_objects_domain_diagnostics import source_domain
from m33_objects_publish_prepare import extend_links


def test_links_deduplicated_without_dropping_old():
    assert extend_links("one\ntwo", ["two", "three"], Path("index.json")) == (
        "one\ntwo\nthree",
        False,
    )


def test_large_new_lists_get_complete_index_pointer_not_truncation():
    old = "a" * 32000
    value, indirect = extend_links(old, ["b" * 2000], Path("index.json"))
    assert indirect
    assert value == old + "\nindex.json"
    with pytest.raises(ValueError):
        extend_links("a" * 32767, ["new"], Path("index.json"))


def test_photo_domain_overrides_publisher_and_missing_is_not_empty_domain():
    assert (
        source_domain(
            {"role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH", "publisher": "commons"}
        )
        == "photographs"
    )
    assert source_domain({"publisher": "openmoji"}) == "openmoji"
    assert source_domain({}) == "sketches_and_absence_control"
