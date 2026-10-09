"""Fresh-author acquisition, resumability and continuation boundary tests."""

import io
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import m33_objects_photo_round as round_data
from m33_objects_photos import author_owner


def test_continuation_does_not_drop_property_pages():
    assert round_data.continuation({}) == {}
    assert (
        round_data.continuation({"continue": {"continue": "gsr||", "gsroffset": 40}})[
            "gsroffset"
        ]
        == 40
    )
    for token in ({"iicontinue": "x"}, {"gsroffset": -1}, {"gsroffset": "40"}, []):
        with pytest.raises(ValueError):
            round_data.continuation({"continue": token})


def test_targeted_scope_is_frozen_and_does_not_collect_other_names(
    tmp_path, monkeypatch
):
    prior = tmp_path / "prior.json"
    prior.write_text(
        json.dumps({"sources": [{"source_id": "commons/1", "author_identity": "old"}]})
    )
    queries = []

    def network(url, limit):
        query = parse_qs(urlparse(url).query)["gsrsearch"][0]
        queries.append(query)
        return b'{"query": {"pages": {}}}'

    monkeypatch.setattr(round_data, "get", network)
    monkeypatch.setattr(round_data, "sheets", lambda *_: None)
    root = tmp_path / "scope"
    result = round_data.acquire(root, [prior], categories=["apple"], pages=1)
    assert result["proposals"] == 0 and len(queries) == len(
        round_data.VARIANTS["apple"]
    )
    assert json.loads((root / "plan.json").read_text())["category_scope"] == ["apple"]
    for names in (["other"], [], ["apple", "apple"]):
        with pytest.raises(ValueError, match="category subset"):
            round_data.acquire(tmp_path / "invalid", [prior], categories=names)


def test_exclusions_bind_all_acquired_authors_and_rejected_ids(tmp_path):
    path = tmp_path / "prior.json"
    path.write_text(
        json.dumps(
            {
                "sources": [{"source_id": "commons/1", "author_identity": "a"}],
                "rejected": [{"source_id": "commons/2"}],
            }
        )
    )
    ids, authors, bindings = round_data.exclusions([path])
    assert ids == {"commons/1", "commons/2"}
    assert authors == {"a"}
    assert bindings[str(path.resolve())] == round_data.sha(path)
    with pytest.raises(ValueError):
        round_data.exclusions([path, path])


def test_pending_round_id_exclusions_do_not_reassign_or_exclude_its_authors(tmp_path):
    old, pending = tmp_path / "old.json", tmp_path / "pending.json"
    old.write_text(
        json.dumps({"sources": [{"source_id": "commons/1", "author_identity": "old"}]})
    )
    pending.write_text(
        json.dumps(
            {"sources": [{"source_id": "commons/2", "author_identity": "pending"}]}
        )
    )
    ids, authors, bindings = round_data.exclusions([old], [pending])
    assert ids == {"commons/1", "commons/2"}
    assert authors == {"old"}
    assert len(bindings) == 2


def page(artist="A fresh author"):
    return {
        "pageid": 3,
        "imageinfo": [
            {
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0"},
                    "Artist": {"value": artist},
                },
                "mime": "image/png",
                "url": "https://upload.wikimedia.org/a.png",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:a.png",
                "sha1": "abc",
            }
        ],
    }


def test_prior_ids_authors_and_author_cap_rejected_before_download(
    tmp_path, monkeypatch
):
    def no_download(*args):
        pytest.fail("Excluded proposal was downloaded")

    monkeypatch.setattr(round_data, "get", no_download)
    identity, _ = author_owner("A fresh author")
    for prior_ids, prior_authors, seen, counts in (
        ({"commons/3"}, set(), set(), Counter()),
        (set(), {identity}, set(), Counter()),
        (set(), set(), {"commons/3"}, Counter()),
        (set(), set(), set(), Counter({("apple", identity): 3})),
    ):
        with pytest.raises(ValueError):
            round_data.candidate(
                page(), "apple", tmp_path, prior_ids, prior_authors, seen, counts
            )


def test_resume_requires_exact_plan_and_unfinished_root(tmp_path):
    prior = tmp_path / "prior.json"
    prior.write_text(
        json.dumps({"sources": [{"source_id": "commons/1", "author_identity": "a"}]})
    )
    root = tmp_path / "run"
    root.mkdir()
    (root / "plan.json").write_text("{}")
    with pytest.raises(ValueError, match="Resume plan changed"):
        round_data.acquire(root, [prior], resume=True)
    (root / "acquisition.json").write_text("{}")
    with pytest.raises(ValueError, match="unfinished"):
        round_data.acquire(root, [prior], resume=True)


def test_resumed_bytes_are_checked_and_cannot_escape(tmp_path):
    with pytest.raises(ValueError, match="escaped"):
        round_data.check_rows(
            [
                {
                    "source_id": "commons/1",
                    "source_file": str(tmp_path.parent / "x"),
                    "source_file_sha256": "bad",
                }
            ],
            tmp_path,
        )


def test_interrupted_acquisition_replays_immutable_page_then_resumes(
    tmp_path, monkeypatch
):
    prior = tmp_path / "prior.json"
    prior.write_text(
        json.dumps(
            {"sources": [{"source_id": "commons/900", "author_identity": "old"}]}
        )
    )
    root = tmp_path / "round"
    image = io.BytesIO()
    Image.new("RGB", (96, 96), "red").save(image, format="PNG")
    interrupted = False

    def network(url, limit):
        nonlocal interrupted
        if url.startswith(round_data.API):
            params = parse_qs(urlparse(url).query)
            offset = int(params.get("gsroffset", [0])[0])
            if offset and not interrupted:
                interrupted = True
                raise KeyboardInterrupt(
                    "simulated interruption after immutable first page"
                )
            item = page()
            item["index"] = offset + 1
            item["pageid"] += offset
            info = item["imageinfo"][0]
            info["url"] = f"https://upload.wikimedia.org/{item['pageid']}.png"
            result = {"query": {"pages": {str(item["pageid"]): item}}}
            if offset == 0:
                result["continue"] = {"continue": "gsr||", "gsroffset": 40}
            return json.dumps(result).encode()
        return image.getvalue()

    monkeypatch.setattr(round_data, "get", network)
    monkeypatch.setattr(round_data, "sheets", lambda *args: None)
    with pytest.raises(KeyboardInterrupt):
        round_data.acquire(root, [prior], positive=2, negative=1, pages=2)
    first_receipt = (root / "receipts/apple-0-0.json").read_bytes()
    result = round_data.acquire(
        root, [prior], positive=2, negative=1, pages=2, resume=True
    )
    assert result["proposals"] == 2
    assert (root / "receipts/apple-0-0.json").read_bytes() == first_receipt
    acquired = json.loads((root / "acquisition.json").read_text())
    assert [r["source_id"] for r in acquired["sources"]] == ["commons/3", "commons/43"]
    with pytest.raises(ValueError, match="unfinished"):
        round_data.acquire(root, [prior], positive=2, negative=1, pages=2, resume=True)
