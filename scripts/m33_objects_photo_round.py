"""Resumable, bounded fresh-photo proposals; no labels inferred from search titles.

Previous source IDs and all previously encountered normalized authors are excluded.
Immutable page receipts allow a interrupted download to resume without resampling.
No training is performed here, and every admitted image needs visual review.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

from m33_objects_data import CLASSES, sha, write_json
from m33_objects_illustrations import normalized
from m33_objects_photos import API, QUERIES, author_owner, get, rights
from PIL import Image, ImageDraw, ImageFont

VARIANTS = {
    "apple": ("apples fruit", "apple isolated fruit", "red green apple fruit"),
    "banana": ("bananas fruit", "banana bunch fruit", "banana isolated fruit"),
    "carrot": ("carrots vegetable", "carrot root vegetable", "carrots harvested"),
    "fish": ("fish underwater", "fish aquarium", "fish freshwater animal"),
    "tree": ("single tree landscape", "tree isolated field", "tree full trunk crown"),
    "mug": ("mug handle", "coffee mug ceramic", "mug cup handle isolated"),
    "chair": ("chair furniture", "wooden chair", "chair isolated furniture"),
    "book": ("closed books stack", "book closed plain", "books spine stack"),
    "pear": ("pears fruit", "pear isolated fruit"),
    "bottle": ("glass bottle isolated", "plastic bottle"),
    "teapot": ("teapot ceramic", "teapot metal"),
    "leaf": ("leaf isolated", "autumn leaf"),
    "dolphin": ("dolphin animal", "dolphin swimming"),
    "spoon": ("spoon isolated", "wooden spoon"),
    "rock": ("stone isolated", "rock stone"),
    "bowl": ("ceramic bowl isolated", "empty bowl"),
}


def exclusions(paths):
    ids, authors, bindings = set(), set(), {}
    for path in paths:
        if str(path.resolve()) in bindings:
            raise ValueError("Repeated prior manifest")
        bindings[str(path.resolve())] = sha(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("sources", [])
        if not rows and "records" in payload:
            rows = [r for cohort in payload["records"].values() for r in cohort]
        for row in rows:
            if row["source_id"].startswith("commons/"):
                ids.add(row["source_id"])
                if row.get("author_identity"):
                    authors.add(row["author_identity"])
        ids.update(
            row["source_id"]
            for row in payload.get("rejected", [])
            if row.get("source_id", "").startswith("commons/")
        )
    if not ids or not authors:
        raise ValueError("Prior photo ID and author exclusions required")
    return ids, authors, bindings


def continuation(payload):
    token = payload.get("continue", {})
    if not isinstance(token, dict) or set(token) - {"continue", "gsroffset"}:
        raise ValueError(
            "Unexpected property continuation; do not discard incomplete pages"
        )
    if token and (type(token.get("gsroffset")) is not int or token["gsroffset"] < 0):
        raise ValueError("Invalid search continuation")
    return token


def check_rows(rows, root):
    seen, author_counts = set(), Counter()
    for row in rows:
        if row["source_id"] in seen:
            raise ValueError("Repeated proposal ID")
        seen.add(row["source_id"])
        for key, digest in (
            ("source_file", "source_file_sha256"),
            ("metadata_file", "metadata_sha256"),
        ):
            path = Path(row[key])
            if (
                not path.resolve().is_relative_to(root.resolve())
                or sha(path) != row[digest]
            ):
                raise ValueError("Resumed photo bytes changed or escaped")
        owner, split = author_owner(row["attribution"])
        if (owner, split) != (row["author_identity"], row["declared_split"]):
            raise ValueError("Resumed photo owner changed")
        author_counts[row["source_category"], owner] += 1
    return seen, author_counts


def candidate(page, category, root, prior_ids, prior_authors, seen, author_counts):
    identity = "commons/" + str(page["pageid"])
    if identity in prior_ids or identity in seen:
        raise ValueError("Previously encountered photo ID")
    info = page["imageinfo"][0]
    name, license_url, artist = rights(info["extmetadata"])
    owner, split = author_owner(artist)
    if owner in prior_authors:
        raise ValueError("Previously encountered normalized author")
    if author_counts[category, owner] >= 3:
        raise ValueError("Three-photo author/category cap")
    url = info.get("thumburl", info["url"])
    if (
        urlparse(url).hostname not in ("upload.wikimedia.org", "thumb.wikimedia.org")
        or urlparse(url).scheme != "https"
        or info["mime"] not in ("image/jpeg", "image/png")
    ):
        raise ValueError("Non-raster or unapproved image host")
    path = root / "images" / (str(page["pageid"]) + ".image")
    # Failed/interrupted downloads can exist. Reuse only when a corresponding
    # immutable download receipt binds the exact URL and bytes.
    download = root / "downloads" / (str(page["pageid"]) + ".json")
    if path.exists():
        if not download.is_file():
            raise ValueError("Unreceipted interrupted file; manual inspection required")
        receipt = json.loads(download.read_text(encoding="utf-8"))
        if receipt != {"url": url, "sha256": sha(path)}:
            raise ValueError("Resumed download URL/bytes mismatch")
    else:
        blob = get(url, 1_000_000)
        with path.open("xb") as stream:
            stream.write(blob)
        write_json(download, {"url": url, "sha256": sha(path)})
    with Image.open(path) as image:
        if (
            image.format not in ("JPEG", "PNG")
            or max(image.size) > 1024
            or min(image.size) < 48
        ):
            raise ValueError("Unexpected photograph dimensions/format")
        image.verify()
    metadata = root / "metadata" / (str(page["pageid"]) + ".json")
    if metadata.exists():
        if json.loads(metadata.read_text(encoding="utf-8")) != page:
            raise ValueError("Resumed metadata changed")
    else:
        write_json(metadata, page)
    return {
        "source_id": identity,
        "source_category": category,
        "publisher": "commons",
        "source_url": info["descriptionurl"],
        "download_url": url,
        "original_url_not_acquired": info["url"],
        "original_sha1_not_verified": info["sha1"],
        "source_file": str(path),
        "source_file_sha256": sha(path),
        "metadata_file": str(metadata),
        "metadata_sha256": sha(metadata),
        "licence": name,
        "licence_url": license_url,
        "attribution": artist,
        "author_identity": owner,
        "declared_split": split,
        "declared_family": "commons/" + owner + "/" + category,
        "proposed_answer": CLASSES.get(category, "UNKNOWN"),
        "modifications": "Bounded source thumbnail; full frame RGB96, no crop; individual source license retained.",
    }


def sheets(root, rows):
    qa = root / "qa"
    qa.mkdir(exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    for category in QUERIES:
        selected = [r for r in rows if r["source_category"] == category]
        for start in range(0, len(selected), 32):
            canvas = Image.new("RGB", (8 * 132, 4 * 132), "white")
            draw = ImageDraw.Draw(canvas)
            for i, row in enumerate(selected[start : start + 32]):
                x, y = (i % 8) * 132, (i // 8) * 132
                canvas.paste(normalized(row["source_file"]), (x + 18, y))
                draw.text(
                    (x + 2, y + 98),
                    f"{start + i}: {row['source_id'].split('/')[-1]}",
                    font=font,
                    fill="blue",
                )
                draw.text(
                    (x + 2, y + 114), row["declared_split"], font=font, fill="black"
                )
            canvas.save(qa / f"{category}-{start:03d}.png")


def acquire(root, previous, *, positive=72, negative=16, pages=3, resume=False):
    if not (1 <= positive <= 120 and 1 <= negative <= 40 and 1 <= pages <= 5):
        raise ValueError("Bounded acquisition budget required")
    prior_ids, prior_authors, bindings = exclusions(previous)
    plan = {
        "schema": 1,
        "previous": bindings,
        "variants": VARIANTS,
        "positive": positive,
        "negative": negative,
        "pages": pages,
        "author_category_cap": 3,
        "all_previous_authors_excluded": True,
        "training_started": False,
    }
    # JSON round trip normalizes the tuple query variants for exact resume checks.
    plan = json.loads(json.dumps(plan))
    if root.exists():
        if not resume or (root / "acquisition.json").exists():
            raise ValueError(
                "Fresh or unfinished explicitly resumed destination required"
            )
        if json.loads((root / "plan.json").read_text(encoding="utf-8")) != plan:
            raise ValueError("Resume plan changed")
    else:
        if resume:
            raise ValueError("Cannot resume missing destination")
        root.mkdir(parents=True)
        for directory in ("images", "metadata", "queries", "downloads", "receipts"):
            (root / directory).mkdir()
        write_json(root / "plan.json", plan)
    sources, rejected = [], []
    for category, variants in VARIANTS.items():
        limit = positive if category in CLASSES else negative
        done = False
        for variant, query in enumerate(variants):
            token = {}
            for number in range(pages):
                key = f"{category}-{variant}-{number}"
                receipt_path = root / "receipts" / (key + ".json")
                params = {
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": query + " filetype:bitmap",
                    "gsrnamespace": 6,
                    "gsrlimit": 40,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata|sha1|size|mime|timestamp",
                    "iiurlwidth": 384,
                } | token
                query_path = root / "queries" / (key + ".json")
                if query_path.exists():
                    payload = query_path.read_bytes()
                else:
                    payload = get(API + "?" + urlencode(params), 3_000_000)
                    with query_path.open("xb") as stream:
                        stream.write(payload)
                result = json.loads(payload)
                if "error" in result:
                    raise ValueError("API query error: " + str(result["error"]))
                token = continuation(result)
                if receipt_path.exists():
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if receipt["params"] != params or receipt["query_sha256"] != sha(
                        query_path
                    ):
                        raise ValueError("Resumed query receipt mismatch")
                else:
                    seen, counts = check_rows(sources, root)
                    admitted, exclusions_page = [], []
                    current = sum(r["source_category"] == category for r in sources)
                    for page in sorted(
                        result.get("query", {}).get("pages", {}).values(),
                        key=lambda p: p["index"],
                    ):
                        if current >= limit:
                            break
                        try:
                            row = candidate(
                                page,
                                category,
                                root,
                                prior_ids,
                                prior_authors,
                                seen,
                                counts,
                            )
                            admitted.append(row)
                            seen.add(row["source_id"])
                            counts[category, row["author_identity"]] += 1
                            current += 1
                        except (
                            ValueError,
                            KeyError,
                            HTTPError,
                            URLError,
                            TimeoutError,
                            OSError,
                        ) as error:
                            exclusions_page.append(
                                {
                                    "source_id": "commons/" + str(page["pageid"]),
                                    "category": category,
                                    "reason": str(error),
                                }
                            )
                    receipt = {
                        "params": params,
                        "query_sha256": sha(query_path),
                        "sources": admitted,
                        "rejected": exclusions_page,
                    }
                    write_json(receipt_path, receipt)
                sources.extend(receipt["sources"])
                rejected.extend(receipt["rejected"])
                seen, counts = check_rows(sources, root)
                if any(
                    r["source_id"] in prior_ids or r["author_identity"] in prior_authors
                    for r in sources
                ):
                    raise ValueError("Prior photo/author leakage")
                if max(counts.values(), default=0) > 3:
                    raise ValueError("Resumed author cap violated")
                current = sum(r["source_category"] == category for r in sources)
                print(
                    json.dumps(
                        {
                            "category": category,
                            "variant": variant,
                            "page": number,
                            "proposals": current,
                        }
                    ),
                    flush=True,
                )
                if current >= limit:
                    done = True
                    break
                if not token:
                    break
            if done:
                break
    for path, digest in bindings.items():
        if sha(Path(path)) != digest:
            raise ValueError("Previous manifest changed during acquisition")
    sheets(root, sources)
    result = {
        "schema": 2,
        "sources": sources,
        "rejected": rejected,
        "queries": VARIANTS,
        "training_started": False,
        "plan_sha256": sha(root / "plan.json"),
        "previous_manifest_sha256": bindings,
        "partition_rule": "SHA256 normalized artist mod100: train<60 dev<70 calibration<85 final otherwise. All previous authors excluded; at most 3 per author/category.",
        "limits": "Proposals only. Mandatory nonblind visual review. Artist aliases/session independence not exhaustive; search metadata is not gold. Full original not acquired. Per-file rights retained.",
    }
    write_json(root / "acquisition.json", result)
    return {
        "proposals": len(sources),
        "rejected_before_review": len(rejected),
        "previous_ids": len(prior_ids),
        "previous_authors": len(prior_authors),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path, action="append", required=True)
    parser.add_argument("--positive", type=int, default=72)
    parser.add_argument("--negative", type=int, default=16)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            acquire(
                args.output,
                args.previous,
                positive=args.positive,
                negative=args.negative,
                pages=args.pages,
                resume=args.resume,
            )
        )
    )
