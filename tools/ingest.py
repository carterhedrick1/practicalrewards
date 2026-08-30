#!/usr/bin/env python3
"""Fetch configured RSS/Atom feeds into the deduplicated daily inbox."""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from common import (
    STATE, fetch_bytes, html_to_text, read_json, resolve_google_news_source_url,
    write_json,
)


BASE_FEEDS = [
    ("Doctor of Credit", "https://www.doctorofcredit.com/category/credit-cards/feed/"),
    ("Frequent Miler", "https://frequentmiler.com/feed/"),
    ("One Mile at a Time", "https://onemileatatime.com/feed/"),
    ("View from the Wing", "https://viewfromthewing.com/feed/"),
    ("The Points Guy", "https://thepointsguy.com/feed/"),
    ("Reddit r/churning", "https://www.reddit.com/r/churning/.rss"),
    ("Reddit r/CreditCards", "https://www.reddit.com/r/CreditCards/.rss"),
]
ISSUERS = ("Chase", "American Express", "Citi", "Capital One")
GOOGLE_NEWS_PATTERN = (
    "https://news.google.com/rss/search?q=%22{issuer}%22+credit+card"
    "&hl=en-US&gl=US&ceid=US:en"
)
FEEDS = BASE_FEEDS + [
    (
        f"Google News: {issuer}",
        GOOGLE_NEWS_PATTERN.format(issuer=urllib.parse.quote_plus(issuer)),
    )
    for issuer in ISSUERS
]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        for child in list(element):
            if local_name(child.tag) == name:
                return "".join(child.itertext()).strip()
    return ""


def atom_link(entry: ET.Element) -> str:
    fallback = ""
    for child in list(entry):
        if local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or child.text or "").strip()
        if not href:
            continue
        if child.attrib.get("rel", "alternate") == "alternate":
            return href
        fallback = fallback or href
    return fallback


def normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed:
            return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return value.strip()


def parse_feed(payload: bytes, configured_source: str, feed_url: str = "") -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    root_kind = local_name(root.tag)
    items: list[dict[str, Any]] = []

    if root_kind in {"rss", "rdf"}:
        channel = next((node for node in root.iter() if local_name(node.tag) == "channel"), root)
        source = child_text(channel, ("title",)) or configured_source
        entries = [node for node in root.iter() if local_name(node.tag) == "item"]
        for entry in entries:
            url = child_text(entry, ("link", "guid"))
            items.append({
                "source": source,
                "title": html_to_text(child_text(entry, ("title",))),
                "url": url.strip(),
                "published": normalize_date(child_text(entry, ("pubdate", "published", "date"))),
                "summary": html_to_text(child_text(entry, ("description", "encoded", "summary", "content"))),
            })
    elif root_kind == "feed":
        source = child_text(root, ("title",)) or configured_source
        entries = [node for node in list(root) if local_name(node.tag) == "entry"]
        for entry in entries:
            items.append({
                "source": source,
                "title": html_to_text(child_text(entry, ("title",))),
                "url": atom_link(entry),
                "published": normalize_date(child_text(entry, ("published", "updated"))),
                "summary": html_to_text(child_text(entry, ("summary", "content"))),
            })
    else:
        raise ValueError(f"unsupported feed root element: {root.tag}")

    usable: list[dict[str, Any]] = []
    for item in items:
        if not item["title"] or not item["url"]:
            continue
        if feed_url:
            item["url"] = urllib.parse.urljoin(feed_url, item["url"])
        usable.append(item)
    return usable


def seen_keys(raw_seen: object) -> tuple[list[dict[str, str]], set[str]]:
    ordered: list[dict[str, str]] = []
    keys: set[str] = set()
    if not isinstance(raw_seen, list):
        raise ValueError("tools/state/seen.json must contain a JSON list")
    for value in raw_seen:
        if isinstance(value, str):
            entry = {"key": value, "seen_at": ""}
        elif isinstance(value, dict) and isinstance(value.get("key"), str):
            entry = {"key": value["key"], "seen_at": str(value.get("seen_at", ""))}
        else:
            continue
        if entry["key"] not in keys:
            ordered.append(entry)
            keys.add(entry["key"])
    return ordered, keys


def ingest() -> list[dict[str, Any]]:
    STATE.mkdir(parents=True, exist_ok=True)
    seen_path = STATE / "seen.json"
    inbox_path = STATE / "inbox.json"
    ordered_seen, known = seen_keys(read_json(seen_path, []))
    new_items: list[dict[str, Any]] = []
    fetched_keys: set[str] = set()
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    for source, url in FEEDS:
        if "reddit.com" in url.lower():
            time.sleep(10)
        try:
            payload, _ = fetch_bytes(url, timeout=15)
            feed_items = parse_feed(payload, source, url)
            print(f"{source}: {len(feed_items)} items", file=sys.stderr)
        except Exception as error:
            print(f"WARNING: skipping {source}: {error}", file=sys.stderr)
            continue

        for item in feed_items:
            try:
                key, unresolved = resolve_google_news_source_url(item["url"], url)
            except Exception as error:
                print(f"WARNING: skipping unsafe feed item URL {item['url']!r}: {error}", file=sys.stderr)
                continue
            if not key or key in known or key in fetched_keys:
                continue
            item["url"] = key
            if unresolved:
                item["unresolved_source"] = True
            fetched_keys.add(key)
            new_items.append(item)

    for key in fetched_keys:
        ordered_seen.append({"key": key, "seen_at": now})
    ordered_seen = ordered_seen[-3000:]
    inbox_existed = inbox_path.exists()
    inbox_before = inbox_path.read_bytes() if inbox_existed else None
    write_json(inbox_path, new_items)
    try:
        write_json(seen_path, ordered_seen)
    except Exception:
        if inbox_existed:
            inbox_path.write_bytes(inbox_before or b"")
        else:
            inbox_path.unlink(missing_ok=True)
        raise
    print(f"Wrote {len(new_items)} new items to {inbox_path}")
    return new_items


def main() -> int:
    ingest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
