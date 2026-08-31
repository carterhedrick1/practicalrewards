#!/usr/bin/env python3
"""Fetch configured RSS/Atom feeds into the deduplicated daily inbox."""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from common import (
    HTTPStatusError, STATE, fetch_bytes, html_to_text, is_google_news_url, read_json,
    resolve_public_http_url, write_json,
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
SEEN_STORY_LIMIT = 3000
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
                value = "".join(child.itertext()).strip()
                if value:
                    return value
    return ""


def child_attribute(element: ET.Element, name: str, attribute: str) -> str:
    for child in list(element):
        if local_name(child.tag) == name:
            return str(child.attrib.get(attribute, "")).strip()
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
    if b"<!doctype" in payload.lower():
        raise ValueError("feed payload contains a prohibited DOCTYPE")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        markup_start = payload.find(b"<")
        if markup_start < 0:
            raise
        cleaned = re.sub(
            rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
            b"",
            payload[markup_start:],
        )
        root = ET.fromstring(cleaned)
    root_kind = local_name(root.tag)
    items: list[dict[str, Any]] = []

    if root_kind in {"rss", "rdf"}:
        channel = next((node for node in root.iter() if local_name(node.tag) == "channel"), root)
        source = child_text(channel, ("title",)) or configured_source
        entries = [node for node in root.iter() if local_name(node.tag) == "item"]
        for entry in entries:
            url = child_text(entry, ("link", "guid"))
            item = {
                "source": source,
                "title": html_to_text(child_text(entry, ("title",))),
                "url": url.strip(),
                "published": normalize_date(child_text(entry, ("pubdate", "published", "date"))),
                "summary": html_to_text(child_text(entry, ("description", "encoded", "summary", "content"))),
            }
            publisher = child_text(entry, ("source",))
            publisher_url = child_attribute(entry, "source", "url")
            if publisher:
                item["publisher"] = publisher
            if publisher_url:
                item["publisher_url"] = publisher_url
            items.append(item)
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


def normalized_fingerprint_text(value: str) -> str:
    value = value.casefold().replace("_", " ")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip(" _")


def publisher_identity_from_url(value: str) -> str:
    try:
        hostname = (urllib.parse.urlsplit(value).hostname or "").rstrip(".").casefold()
    except ValueError:
        return ""
    labels = [label for label in hostname.split(".") if label and label != "www"]
    if not labels:
        return ""
    common_second_level_suffixes = {
        "co.uk", "org.uk", "com.au", "net.au", "co.nz", "co.jp", "co.in",
    }
    suffix = ".".join(labels[-2:])
    label_index = -3 if len(labels) >= 3 and suffix in common_second_level_suffixes else -2
    registrable_label = labels[label_index] if len(labels) >= abs(label_index) else labels[0]
    return re.sub(r"[^a-z0-9]+", "", registrable_label)


def _fingerprint(publisher: str, title: str) -> str:
    normalized_title = normalized_fingerprint_text(title)
    if not normalized_title:
        return ""
    identity = re.sub(r"[^a-z0-9]+", "", normalized_fingerprint_text(publisher))
    material = f"{identity}|{normalized_title}" if identity else normalized_title
    return "v1:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def legacy_url_fingerprint(url: str) -> str:
    """Derive a best-effort fingerprint while migrating URL-only seen records."""
    if is_google_news_url(url):
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if hostname == "reddit.com" or hostname.endswith(".reddit.com"):
        return ""
    slug = urllib.parse.unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1])
    return _fingerprint(publisher_identity_from_url(url), slug)


def item_fingerprints(item: dict[str, Any], url: str) -> list[str]:
    title = str(item.get("title", ""))
    publisher = ""
    if is_google_news_url(url):
        publisher_url = str(item.get("publisher_url", ""))
        publisher = publisher_identity_from_url(publisher_url)
        publisher_name = str(item.get("publisher", "")).strip()
        title_match = re.fullmatch(r"(.+)\s+[-–—]\s+(.+)", title)
        if title_match:
            title_stem, title_suffix = title_match.groups()
            suffix_identity = re.sub(
                r"[^a-z0-9]+", "", normalized_fingerprint_text(title_suffix)
            )
            publisher_name_identity = re.sub(
                r"[^a-z0-9]+", "", normalized_fingerprint_text(publisher_name)
            )
            if not publisher_name:
                publisher_name = title_suffix.strip()
                publisher_name_identity = suffix_identity
            if not publisher or suffix_identity in {publisher, publisher_name_identity}:
                title = title_stem.strip()
        if not publisher:
            publisher = publisher_name
        if not publisher:
            summary = str(item.get("summary", ""))
            if summary.casefold().startswith(title.casefold()):
                publisher = summary[len(title):].strip(" -–—|:")
    else:
        publisher = publisher_identity_from_url(url)

    fingerprints = [_fingerprint(publisher, title)]
    legacy = legacy_url_fingerprint(url)
    if legacy:
        fingerprints.append(legacy)
    return list(dict.fromkeys(value for value in fingerprints if value))


def _record_urls(record: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys([
        str(record.get("key", "")),
        *[str(value) for value in record.get("aliases", [])],
    ]))


def _merge_seen_record(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    urls = list(dict.fromkeys(_record_urls(target) + _record_urls(incoming)))
    target["key"] = urls[0]
    if len(urls) > 1:
        target["aliases"] = urls[1:]
    else:
        target.pop("aliases", None)
    fingerprints = list(dict.fromkeys([
        *[str(value) for value in target.get("fingerprints", [])],
        *[str(value) for value in incoming.get("fingerprints", [])],
    ]))
    fingerprints = [value for value in fingerprints if value]
    if fingerprints:
        target["fingerprints"] = fingerprints


def seen_records(raw_seen: object) -> list[dict[str, Any]]:
    """Normalize legacy/new seen entries and coalesce matching story records."""
    entries: list[dict[str, Any]] = []
    if not isinstance(raw_seen, list):
        raise ValueError("tools/state/seen.json must contain a JSON list")
    for value in raw_seen:
        if isinstance(value, str):
            entry: dict[str, Any] = {"key": value, "seen_at": ""}
        elif isinstance(value, dict) and isinstance(value.get("key"), str):
            aliases = value.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            elif not isinstance(aliases, list):
                aliases = []
            fingerprints = value.get("fingerprints", [])
            if isinstance(fingerprints, str):
                fingerprints = [fingerprints]
            elif not isinstance(fingerprints, list):
                fingerprints = []
            if isinstance(value.get("fingerprint"), str):
                fingerprints = [value["fingerprint"], *fingerprints]
            entry = {
                "key": value["key"],
                "seen_at": str(value.get("seen_at", "")),
            }
            clean_aliases = [alias for alias in aliases if isinstance(alias, str) and alias]
            clean_fingerprints = [
                fingerprint for fingerprint in fingerprints
                if isinstance(fingerprint, str) and fingerprint
            ]
            if clean_aliases:
                entry["aliases"] = list(dict.fromkeys(clean_aliases))
            if clean_fingerprints:
                entry["fingerprints"] = list(dict.fromkeys(clean_fingerprints))
        else:
            continue
        if not entry["key"]:
            continue
        legacy_fingerprints = [
            legacy_url_fingerprint(url) for url in _record_urls(entry)
        ]
        if any(legacy_fingerprints):
            entry["fingerprints"] = list(dict.fromkeys([
                *entry.get("fingerprints", []),
                *[fingerprint for fingerprint in legacy_fingerprints if fingerprint],
            ]))

        entries.append(entry)

    parents = list(range(len(entries)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        older, newer = sorted((left_root, right_root))
        parents[newer] = older

    owners: dict[tuple[str, str], int] = {}
    for index, entry in enumerate(entries):
        tokens = [
            *[("url", url) for url in _record_urls(entry)],
            *[("fingerprint", value) for value in entry.get("fingerprints", [])],
        ]
        for token in tokens:
            if token in owners:
                union(index, owners[token])
            else:
                owners[token] = index

    ordered: list[dict[str, Any]] = []
    merged_by_root: dict[int, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        root = find(index)
        if root not in merged_by_root:
            merged_by_root[root] = entry
            ordered.append(entry)
        else:
            _merge_seen_record(merged_by_root[root], entry)
    return ordered


def seen_keys(raw_seen: object) -> tuple[list[dict[str, Any]], set[str]]:
    """Backward-compatible view of normalized records and all URL aliases."""
    ordered = seen_records(raw_seen)
    return ordered, {url for record in ordered for url in _record_urls(record)}


def record_seen_aliases(path: Path, pairs: list[tuple[str, str]]) -> None:
    """Attach resolved publisher URLs to their wrapper story records."""
    if not pairs:
        return
    records = seen_records(read_json(path, []))
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for original_url, alias_url in pairs:
        owner = next(
            (record for record in records if original_url in _record_urls(record)),
            None,
        )
        if owner is None:
            owner = {"key": original_url, "seen_at": now}
            records.append(owner)
        _merge_seen_record(owner, {
            "key": original_url,
            "aliases": [alias_url],
            "fingerprints": [legacy_url_fingerprint(alias_url)],
            "seen_at": owner.get("seen_at", now),
        })
    write_json(path, seen_records(records)[-SEEN_STORY_LIMIT:])


def ingest() -> list[dict[str, Any]]:
    STATE.mkdir(parents=True, exist_ok=True)
    seen_path = STATE / "seen.json"
    inbox_path = STATE / "inbox.json"
    ordered_seen = seen_records(read_json(seen_path, []))
    known_urls = {
        url: record for record in ordered_seen for url in _record_urls(record)
    }
    known_fingerprints = {
        fingerprint: record
        for record in ordered_seen
        for fingerprint in record.get("fingerprints", [])
    }
    new_items: list[dict[str, Any]] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    for source, url in FEEDS:
        if "reddit.com" in url.lower():
            time.sleep(10)
        try:
            for attempt in range(2):
                try:
                    payload, _ = fetch_bytes(url, timeout=15)
                    break
                except HTTPStatusError as error:
                    if error.status != 429 or attempt:
                        raise
                    delay = 15.0
                    if error.retry_after:
                        try:
                            delay = float(error.retry_after)
                        except ValueError:
                            try:
                                retry_at = email.utils.parsedate_to_datetime(error.retry_after)
                                if retry_at.tzinfo is None:
                                    retry_at = retry_at.replace(tzinfo=dt.timezone.utc)
                                delay = (
                                    retry_at - dt.datetime.now(dt.timezone.utc)
                                ).total_seconds()
                            except (TypeError, ValueError, OverflowError):
                                delay = 15.0
                    delay = min(60.0, max(0.0, delay))
                    print(
                        f"WARNING: {source} returned HTTP 429; retrying in {delay:g}s",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
            feed_items = parse_feed(payload, source, url)
            print(f"{source}: {len(feed_items)} items", file=sys.stderr)
        except Exception as error:
            print(f"WARNING: skipping {source}: {error}", file=sys.stderr)
            continue

        for item in feed_items:
            try:
                key = resolve_public_http_url(item["url"], url)
            except Exception as error:
                print(f"WARNING: skipping unsafe feed item URL {item['url']!r}: {error}", file=sys.stderr)
                continue
            fingerprints = item_fingerprints(item, key)
            existing = known_urls.get(key) or next(
                (known_fingerprints[value] for value in fingerprints if value in known_fingerprints),
                None,
            )
            if existing is not None:
                _merge_seen_record(existing, {
                    "key": key,
                    "fingerprints": fingerprints,
                    "seen_at": existing.get("seen_at", now),
                })
                for known_url in _record_urls(existing):
                    known_urls[known_url] = existing
                for fingerprint in existing.get("fingerprints", []):
                    known_fingerprints[fingerprint] = existing
                continue
            item["url"] = key
            if is_google_news_url(key):
                item["needs_resolution"] = True
            record = {"key": key, "fingerprints": fingerprints, "seen_at": now}
            ordered_seen.append(record)
            known_urls[key] = record
            for fingerprint in fingerprints:
                known_fingerprints[fingerprint] = record
            new_items.append(item)

    ordered_seen = ordered_seen[-SEEN_STORY_LIMIT:]
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
