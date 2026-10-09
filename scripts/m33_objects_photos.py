"""Bounded Commons proposals with per-file rights and author-owned partitions."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from m33_objects_data import CLASSES, sha, write_json
from m33_objects_illustrations import normalized
from PIL import Image, ImageDraw, ImageFont

API = "https://commons.wikimedia.org/w/api.php"
QUERIES = {
    "apple": "apple fruit",
    "banana": "banana fruit",
    "carrot": "carrots vegetable",
    "fish": "fish animal underwater",
    "tree": "single tree field",
    "mug": "ceramic mug",
    "chair": "chair furniture",
    "book": "stack books",
    "pear": "pear fruit",
    "bottle": "glass bottle",
    "teapot": "teapot",
    "leaf": "leaf isolated",
    "dolphin": "dolphin",
    "spoon": "spoon",
    "rock": "stone rock isolated",
    "bowl": "ceramic bowl",
}
USER_AGENT = "ai-brain-educational-research/1.0 (bounded Commons image collection)"


def rights(metadata):
    name = metadata.get("LicenseShortName", {}).get("value", "")
    url = metadata.get("LicenseUrl", {}).get("value", "")
    artist = metadata.get("Artist", {}).get("value", "")
    if not artist or not (
        name in ("CC0", "Public domain")
        or re.fullmatch(r"CC BY(?:-SA)? [1-4]\.0", name)
    ):
        raise ValueError("Explicit permissive per-file rights and author required")
    if name.startswith("CC BY"):
        kind, version = name.split()[1:]
        expected = rf"https?://creativecommons\.org/licenses/{kind.lower()}/{re.escape(version)}/?"
        if not re.fullmatch(expected, url):
            raise ValueError("CC license name/version differs from official URL")
    return name, url, artist


def author_owner(artist):
    plain = html.unescape(re.sub("<[^>]+>", "", artist)).strip().casefold()
    if not plain:
        raise ValueError("Missing normalized artist")
    identity = hashlib.sha256(plain.encode()).hexdigest()
    n = int(identity[:8], 16) % 100
    split = (
        "train" if n < 60 else "dev" if n < 70 else "calibration" if n < 85 else "final"
    )
    return identity, split


def get(url, limit):
    for attempt in range(3):
        time.sleep(0.35)
        try:
            with urlopen(
                Request(url, headers={"User-Agent": USER_AGENT}), timeout=45
            ) as response:
                payload = response.read(limit + 1)
            break
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = int(error.headers.get("Retry-After", "10"))
            if delay > 60:
                raise
            print(
                json.dumps({"retry_http": error.code, "wait_seconds": delay}),
                flush=True,
            )
            remaining = delay
            while remaining > 0:
                pause = min(15, remaining)
                time.sleep(pause)
                remaining -= pause
    if len(payload) > limit:
        raise ValueError("Acquisition byte budget exceeded")
    return payload


def acquire(root, positive=40, negative=20, cached_queries=None):
    if (
        root.exists()
        or not 1 <= min(positive, negative) <= max(positive, negative) <= 60
    ):
        raise ValueError("Fresh bounded photo acquisition required")
    root.mkdir(parents=True)
    (root / "images").mkdir()
    (root / "metadata").mkdir()
    (root / "queries").mkdir()
    sources, rejected, seen = [], [], set()
    for category, query in QUERIES.items():
        limit = positive if category in CLASSES else negative
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query + " filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|sha1|size|mime|timestamp",
            "iiurlwidth": 384,
        }
        cached = cached_queries / (category + ".json") if cached_queries else None
        payload = (
            cached.read_bytes()
            if cached and cached.is_file()
            else get(API + "?" + urlencode(params), 3_000_000)
        )
        (root / "queries" / (category + ".json")).write_bytes(payload)
        pages = json.loads(payload).get("query", {}).get("pages", {})
        for page in sorted(pages.values(), key=lambda p: p["index"]):
            identity = "commons/" + str(page["pageid"])
            if identity in seen:
                rejected.append(
                    {"source_id": identity, "reason": "Repeated search result"}
                )
                continue
            seen.add(identity)
            try:
                info = page["imageinfo"][0]
                name, license_url, artist = rights(info["extmetadata"])
                owner, split = author_owner(artist)
                url = info.get("thumburl", info["url"])
                if (
                    urlparse(url).hostname
                    not in ("upload.wikimedia.org", "thumb.wikimedia.org")
                    or urlparse(url).scheme != "https"
                    or info["mime"] not in ("image/jpeg", "image/png")
                ):
                    raise ValueError("Non-raster or unapproved image host")
                filename = str(page["pageid"])
                path = root / "images" / (filename + ".image")
                blob = get(url, 1_000_000)
                with path.open("xb") as stream:
                    stream.write(blob)
                with Image.open(path) as image:
                    if (
                        image.format not in ("JPEG", "PNG")
                        or max(image.size) > 1024
                        or min(image.size) < 48
                    ):
                        raise ValueError("Unexpected photograph dimensions/format")
                    image.verify()
                metadata_path = root / "metadata" / (filename + ".json")
                write_json(metadata_path, page)
                sources.append(
                    {
                        "source_id": identity,
                        "source_category": category,
                        "publisher": "commons",
                        "source_url": info["descriptionurl"],
                        "download_url": url,
                        "original_url_not_acquired": info["url"],
                        "original_sha1_not_verified": info["sha1"],
                        "source_file": str(path),
                        "source_file_sha256": sha(path),
                        "metadata_file": str(metadata_path),
                        "metadata_sha256": sha(metadata_path),
                        "licence": name,
                        "licence_url": license_url,
                        "attribution": artist,
                        "author_identity": owner,
                        "declared_split": split,
                        "declared_family": "commons/" + owner + "/" + category,
                        "proposed_answer": CLASSES.get(category, "UNKNOWN"),
                        "modifications": "Downloaded bounded source thumbnail; full frame centered at RGB96, no crop. Derivatives retain individual source license.",
                    }
                )
            except (ValueError, KeyError, HTTPError, URLError, TimeoutError) as error:
                rejected.append({"source_id": identity, "reason": str(error)})
        print(
            json.dumps(
                {
                    "category": category,
                    "proposals": sum(r["source_category"] == category for r in sources),
                }
            ),
            flush=True,
        )
    write_json(
        root / "acquisition.json",
        {
            "schema": 1,
            "sources": sources,
            "rejected": rejected,
            "queries": QUERIES,
            "training_started": False,
            "partition_rule": "SHA256 normalized artist mod100: train<60 dev<70 calibration<85 final otherwise. All categories by same normalized author have one owner.",
            "limits": "Search titles/metadata are proposals, not truth. Mandatory visual review; author strings do not guarantee exhaustive aliases/session independence. Full original bytes not acquired. Per-image license/attribution retained; no blanket Commons license.",
        },
    )
    qa = root / "qa"
    qa.mkdir()
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    for category in QUERIES:
        rows = [r for r in sources if r["source_category"] == category]
        canvas = Image.new(
            "RGB", (8 * 132, max(1, (len(rows) + 7) // 8) * 132), "white"
        )
        draw = ImageDraw.Draw(canvas)
        for i, row in enumerate(rows):
            x, y = (i % 8) * 132, (i // 8) * 132
            canvas.paste(normalized(row["source_file"]), (x + 18, y))
            draw.text(
                (x + 2, y + 98),
                f"{i}: {row['source_id'].split('/')[-1]}",
                font=font,
                fill="blue",
            )
            draw.text((x + 2, y + 114), row["declared_split"], font=font, fill="black")
        canvas.save(qa / (category + ".png"))
    return {"proposals": len(sources), "rejected_before_review": len(rejected)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cached-queries", type=Path)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output, cached_queries=args.cached_queries)))
