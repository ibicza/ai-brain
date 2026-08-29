"""Bounded inert adapters used by the sealed M-33 source acquisition CLI."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT = "ai-brain-m33-bounded-acquisition/1.0"


@dataclass(frozen=True)
class Snapshot:
    name: str
    data: bytes
    source_selector: str
    transformation_id: str


def download(url: str, allowed: set[str], maximum: int):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed:
        raise ValueError("source selector escapes sealed authority domains")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if final.scheme != "https" or final.hostname not in allowed:
            raise ValueError("source redirect escapes sealed authority domains")
        data = response.read(maximum + 1)
        if not data or len(data) > maximum:
            raise ValueError("downloaded source violates resource bounds")
        headers = {key.casefold(): value for key, value in response.headers.items()}
    return data, headers, final_url


def snapshots(resource: dict, downloaded: bytes) -> tuple[Snapshot, ...]:
    adapter = resource["adapter"]
    if adapter == "raw_text":
        text = downloaded.decode("utf-8", errors="strict")
        return (
            Snapshot(
                Path(urllib.parse.urlparse(resource["url"]).path).stem,
                lf_bytes(text),
                resource["url"],
                "utf8-lf-normalization.v1",
            ),
        )
    if adapter == "static_html":
        text = visible_text(downloaded.decode("utf-8", errors="strict"))
        return (
            Snapshot(
                Path(urllib.parse.urlparse(resource["url"]).path).stem,
                lf_bytes(text),
                resource["url"],
                "static-visible-html-text.v1",
            ),
        )
    if adapter == "wordpress_api":
        rows = json.loads(downloaded, object_pairs_hook=strict_object)
        pattern = re.compile(resource["selector"]["title_regex"])
        result = []
        for row in rows:
            title = html.unescape(row["title"]["rendered"]).strip()
            if not pattern.search(title):
                continue
            text = title + "\n\n" + visible_text(row["content"]["rendered"])
            result.append(
                Snapshot(
                    row["slug"],
                    lf_bytes(text),
                    f"wordpress:{row['id']}:{row['modified']}",
                    "wordpress-visible-chapter-text.v1",
                )
            )
        if not result:
            raise ValueError("sealed WordPress selector matched no chapters")
        return tuple(result)
    raise ValueError("unknown sealed source adapter")


class _VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        del attrs
        if tag.casefold() in {
            "script",
            "style",
            "iframe",
            "object",
            "embed",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
        }:
            self.blocked += 1
        elif not self.blocked and tag.casefold() in {
            "p",
            "div",
            "section",
            "article",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "pre",
            "code",
        }:
            self.fragments.append("\n")

    def handle_endtag(self, tag):
        if tag.casefold() in {
            "script",
            "style",
            "iframe",
            "object",
            "embed",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
        }:
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if not self.blocked:
            self.fragments.append(data)


def visible_text(value: str) -> str:
    parser = _VisibleHTML()
    parser.feed(value)
    parser.close()
    lines = (" ".join(item.split()) for item in "".join(parser.fragments).splitlines())
    return "\n".join(item for item in lines if item)


def lf_bytes(text: str) -> bytes:
    return (text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n").encode(
        "utf-8"
    )


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", value.casefold()).strip("-") or "source"


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result
