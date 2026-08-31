#!/usr/bin/env python3
"""Shared stdlib-only helpers for the Practical Rewards content pipeline."""

from __future__ import annotations

import base64
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
STATE = TOOLS / "state"
USER_AGENT = "PracticalRewardsBot/1.0 (+https://practicalrewards.com)"
FETCH_TIMEOUT = 15
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5

BLOG_COMPONENT_CLASS_WHITELIST = frozenset({
    "pr-verdict",
    "pr-math",
    "pr-math-row",
    "pr-math-label",
    "pr-math-amount",
    "pr-math-total",
    "pr-steps",
    "pr-step",
    "pr-step-number",
    "pr-step-body",
    "pr-catch",
    "pr-compare",
})


ISSUER_ALIASES = {
    "amex": ("american express", "amex"),
    "bank-of-america": ("bank of america", "bofa"),
    "barclays": ("barclays",),
    "bilt": ("bilt",),
    "capital-one": ("capital one",),
    "chase": ("chase",),
    "citi": ("citi",),
    "discover": ("discover",),
    "fidelity": ("fidelity",),
    "paypal": ("paypal",),
    "us-bank": ("u s bank", "us bank"),
    "wells-fargo": ("wells fargo",),
}

_GENERIC_PRODUCT_SUFFIXES = (("credit", "card"), ("card",), ("by",), ("from",))
_NETWORK_SUFFIXES = (
    ("world", "elite", "mastercard"),
    ("world", "mastercard"),
    ("visa", "infinite"),
    ("visa", "signature"),
    ("mastercard",),
    ("visa",),
)


def normalize_card_text(value: str) -> str:
    """Normalize display text for punctuation-insensitive card-name matching."""
    value = re.sub(r"[®™℠]", "", value or "")
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalized_text_positions(value: str) -> tuple[str, list[int]]:
    """Return normalized text plus a map from normalized to original offsets."""
    characters: list[str] = []
    positions: list[int] = []
    pending_space_at: int | None = None
    for index, character in enumerate(value or ""):
        folded = character.casefold()
        emitted = False
        for output in folded:
            if "a" <= output <= "z" or "0" <= output <= "9":
                if pending_space_at is not None and characters:
                    characters.append(" ")
                    positions.append(pending_space_at)
                pending_space_at = None
                characters.append(output)
                positions.append(index)
                emitted = True
        if not emitted:
            pending_space_at = index
    return "".join(characters), positions


def issuer_aliases(card: dict[str, Any]) -> set[str]:
    return {
        normalize_card_text(alias)
        for alias in ISSUER_ALIASES.get(str(card.get("bank_type", "")), ())
        if normalize_card_text(alias)
    }


def card_product_aliases(card: dict[str, Any], include_single: bool = False) -> set[str]:
    """Derive issuer-free product phrases such as Venture X or Sapphire Reserve."""
    product = normalize_card_text(str(card.get("name", "")))
    for issuer in sorted(issuer_aliases(card), key=len, reverse=True):
        product = re.sub(rf"(?<![a-z0-9]){re.escape(issuer)}(?![a-z0-9])", " ", product)
    tokens = product.split()
    changed = True
    while changed and tokens:
        changed = False
        for suffix in _NETWORK_SUFFIXES + _GENERIC_PRODUCT_SUFFIXES:
            if len(tokens) >= len(suffix) and tuple(tokens[-len(suffix):]) == suffix:
                del tokens[-len(suffix):]
                changed = True
                break
    if not tokens or (len(tokens) == 1 and not include_single):
        return set()
    return {" ".join(tokens)}


def card_aliases(card: dict[str, Any]) -> set[str]:
    """Build normalized full-name, issuer-variant, and distinctive-product aliases."""
    canonical = normalize_card_text(str(card.get("name", "")))
    if not canonical:
        return set()
    aliases = {canonical}
    issuers = issuer_aliases(card)
    product_phrases = card_product_aliases(card, include_single=True)
    for product in product_phrases:
        aliases.update(f"{issuer} {product}" for issuer in issuers)
        aliases.update(f"{product} {issuer}" for issuer in issuers)
        if len(product.split()) >= 2:
            aliases.add(product)
    for alias in list(aliases):
        tokens = alias.split()
        if tokens and tokens[-1] == "card":
            tokens.pop()
        if tokens:
            aliases.add(" ".join(tokens))
    return {alias for alias in aliases if alias}


def card_alias_index(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return only aliases owned by one card; ambiguous aliases are unusable."""
    owners: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        for alias in card_aliases(card):
            owners.setdefault(alias, []).append(card)
    return {
        alias: owned[0]
        for alias, owned in owners.items()
        if len({card.get("id") for card in owned}) == 1
    }


def unambiguous_card_aliases(
    card: dict[str, Any],
    cards: list[dict[str, Any]],
) -> set[str]:
    index = card_alias_index(cards)
    return {
        alias for alias in card_aliases(card)
        if alias in index and index[alias].get("id") == card.get("id")
    }


def normalized_phrase_in_text(phrase: str, value: str) -> bool:
    phrase = normalize_card_text(phrase)
    normalized = normalize_card_text(value)
    if not phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized) is not None


def card_mentions(
    value: str,
    cards: list[dict[str, Any]],
) -> list[tuple[int, int, dict[str, Any], str]]:
    """Find card aliases and return their spans in the original string."""
    normalized, positions = _normalized_text_positions(value)
    if not normalized:
        return []
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    for alias, card in sorted(card_alias_index(cards).items(), key=lambda item: len(item[0]), reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, normalized):
            start = positions[match.start()]
            end = positions[match.end() - 1] + 1
            candidates.append((start, end, card, alias))

    # Prefer a card's longest alias when full and shortened aliases overlap.
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), str(item[2].get("id", ""))))
    mentions: list[tuple[int, int, dict[str, Any], str]] = []
    for candidate in candidates:
        start, end, card, _ = candidate
        if any(start < existing[1] and end > existing[0] for existing in mentions):
            continue
        mentions.append(candidate)
    return sorted(mentions, key=lambda item: (item[0], item[1]))


def card_is_mentioned(value: str, card: dict[str, Any]) -> bool:
    return bool(card_mentions(value, [card]))


class TextExtractor(HTMLParser):
    """Extract readable text while dropping script, style, and other chrome."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
    BLOCK_TAGS = {
        "article", "aside", "blockquote", "br", "div", "figcaption", "footer",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "nav",
        "ol", "p", "section", "span", "table", "td", "th", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif not self._skip_depth and tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth and tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()


class GoogleNewsTargetExtractor(HTMLParser):
    """Collect publisher targets exposed by a Google News interstitial."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attribute_targets: list[str] = []
        self.external_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value for name, value in attrs if value}
        target = values.get("data-n-au")
        if target:
            self.attribute_targets.append(target.strip())
        if tag == "a":
            href = values.get("href")
            if href and _is_external_non_google_url(href):
                self.external_hrefs.append(href.strip())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class ContentHTMLValidator(HTMLParser):
    """Validate the exact passive markup subset accepted for article bodies."""

    ALLOWED_TAGS = {
        "h2", "h3", "p", "strong", "ul", "ol", "li",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td",
        "div", "section", "span",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower not in self.ALLOWED_TAGS:
            self.problems.append(f"tag <{tag}> is not allowed")
        if lower in {"div", "section", "span"}:
            if len(attrs) != 1 or attrs[0][0].casefold() != "class":
                self.problems.append(
                    f"<{tag}> requires class as its sole attribute"
                )
            else:
                class_names = (attrs[0][1] or "").split()
                invalid_classes = sorted({
                    name for name in class_names
                    if name not in BLOG_COMPONENT_CLASS_WHITELIST
                })
                if not class_names:
                    self.problems.append(f"<{tag}> requires a non-empty class value")
                elif invalid_classes:
                    self.problems.append(
                        f"classes are not allowed on <{tag}>: {', '.join(invalid_classes)}"
                    )
        elif attrs:
            names = ", ".join(name for name, _ in attrs)
            self.problems.append(f"attributes are not allowed on <{tag}>: {names}")
        self.stack.append(lower)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.problems.append(f"self-closing tag <{tag}/> is not allowed")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower not in self.ALLOWED_TAGS:
            self.problems.append(f"closing tag </{tag}> is not allowed")
        if not self.stack:
            self.problems.append(f"closing tag </{tag}> has no opener")
        elif self.stack[-1] != lower:
            self.problems.append(f"misnested closing tag </{tag}>")
            if lower in self.stack:
                while self.stack and self.stack[-1] != lower:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()
        else:
            self.stack.pop()

    def handle_comment(self, data: str) -> None:
        self.problems.append("HTML comments are not allowed")

    def handle_decl(self, decl: str) -> None:
        self.problems.append("HTML declarations are not allowed")

    def handle_pi(self, data: str) -> None:
        self.problems.append("processing instructions are not allowed")

    def finish(self) -> None:
        if self.stack:
            self.problems.append("unclosed tags: " + ", ".join(self.stack[-8:]))


def html_to_text(value: str) -> str:
    parser = TextExtractor()
    try:
        parser.feed(value or "")
        parser.close()
    except Exception:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()
    return parser.text()


def validate_content_html(value: str) -> None:
    parser = ContentHTMLValidator()
    try:
        parser.feed(value)
        parser.close()
        parser.finish()
    except Exception as error:
        raise ValueError(f"content_html could not be parsed: {error}") from error
    if parser.problems:
        raise ValueError("invalid content_html: " + "; ".join(parser.problems))


def _valid_png(data: bytes) -> bool:
    position = 8
    dimensions: tuple[int, int] | None = None
    saw_image_data = False
    while position + 12 <= len(data):
        length = int.from_bytes(data[position:position + 4], "big")
        chunk_type = data[position + 4:position + 8]
        chunk_end = position + 12 + length
        if chunk_end > len(data):
            return False
        payload = data[position + 8:position + 8 + length]
        expected_crc = int.from_bytes(data[position + 8 + length:chunk_end], "big")
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            return False
        if position == 8:
            if chunk_type != b"IHDR" or length != 13:
                return False
            dimensions = (
                int.from_bytes(payload[0:4], "big"),
                int.from_bytes(payload[4:8], "big"),
            )
        elif chunk_type == b"IDAT" and length > 0:
            saw_image_data = True
        if chunk_type == b"IEND":
            return length == 0 and chunk_end == len(data) and saw_image_data and bool(
                dimensions and dimensions[0] > 0 and dimensions[1] > 0
            )
        position = chunk_end
    return False


def _valid_jpeg(data: bytes) -> bool:
    if len(data) < 12 or not data.endswith(b"\xff\xd9"):
        return False
    position = 2
    dimensions: tuple[int, int] | None = None
    saw_scan_data = False
    standalone = {0x01, *range(0xD0, 0xDA)}
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while position < len(data) - 2:
        if data[position] != 0xFF:
            return False
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return False
        marker = data[position]
        position += 1
        if marker == 0xDA:
            if position + 2 > len(data):
                return False
            segment_length = int.from_bytes(data[position:position + 2], "big")
            scan_start = position + segment_length
            if segment_length < 2 or scan_start >= len(data) - 2:
                return False
            saw_scan_data = True
            break
        if marker in standalone:
            continue
        if position + 2 > len(data):
            return False
        segment_length = int.from_bytes(data[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            return False
        if marker in start_of_frame:
            if segment_length < 7:
                return False
            dimensions = (
                int.from_bytes(data[position + 5:position + 7], "big"),
                int.from_bytes(data[position + 3:position + 5], "big"),
            )
        position += segment_length
    return saw_scan_data and bool(dimensions and dimensions[0] > 0 and dimensions[1] > 0)


def _skip_gif_subblocks(data: bytes, position: int) -> int | None:
    while position < len(data):
        length = data[position]
        position += 1
        if length == 0:
            return position
        position += length
        if position > len(data):
            return None
    return None


def _valid_gif(data: bytes) -> bool:
    if len(data) < 14:
        return False
    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    if not width or not height:
        return False
    packed = data[10]
    position = 13
    if packed & 0x80:
        position += 3 * (2 ** ((packed & 0x07) + 1))
    while position < len(data):
        marker = data[position]
        position += 1
        if marker == 0x3B:
            return position == len(data)
        if marker == 0x21:
            if position >= len(data):
                return False
            position += 1
            next_position = _skip_gif_subblocks(data, position)
            if next_position is None:
                return False
            position = next_position
            continue
        if marker != 0x2C or position + 9 > len(data):
            return False
        descriptor = data[position:position + 9]
        position += 9
        if descriptor[8] & 0x80:
            position += 3 * (2 ** ((descriptor[8] & 0x07) + 1))
        if position >= len(data):
            return False
        position += 1
        next_position = _skip_gif_subblocks(data, position)
        if next_position is None:
            return False
        position = next_position
    return False


def _valid_webp(data: bytes) -> bool:
    if len(data) < 20 or int.from_bytes(data[4:8], "little") + 8 != len(data):
        return False
    position = 12
    dimensions: tuple[int, int] | None = None
    while position + 8 <= len(data):
        chunk_type = data[position:position + 4]
        length = int.from_bytes(data[position + 4:position + 8], "little")
        payload_start = position + 8
        payload_end = payload_start + length
        next_position = payload_end + (length & 1)
        if payload_end > len(data) or next_position > len(data):
            return False
        payload = data[payload_start:payload_end]
        if chunk_type == b"VP8X" and length >= 10:
            dimensions = (
                int.from_bytes(payload[4:7], "little") + 1,
                int.from_bytes(payload[7:10], "little") + 1,
            )
        elif chunk_type == b"VP8L" and length >= 5 and payload[0] == 0x2F:
            packed_dimensions = int.from_bytes(payload[1:5], "little")
            dimensions = (
                (packed_dimensions & 0x3FFF) + 1,
                ((packed_dimensions >> 14) & 0x3FFF) + 1,
            )
        elif chunk_type == b"VP8 " and length >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            dimensions = (
                int.from_bytes(payload[6:8], "little") & 0x3FFF,
                int.from_bytes(payload[8:10], "little") & 0x3FFF,
            )
        position = next_position
    return position == len(data) and bool(
        dimensions and dimensions[0] > 0 and dimensions[1] > 0
    )


def _valid_avif(data: bytes) -> bool:
    position = 0
    saw_ftyp = False
    saw_media_data = False
    while position < len(data):
        if position + 8 > len(data):
            return False
        box_length = int.from_bytes(data[position:position + 4], "big")
        box_type = data[position + 4:position + 8]
        header_length = 8
        if box_length == 1:
            if position + 16 > len(data):
                return False
            box_length = int.from_bytes(data[position + 8:position + 16], "big")
            header_length = 16
        elif box_length == 0:
            box_length = len(data) - position
        if box_length < header_length or position + box_length > len(data):
            return False
        if box_type == b"ftyp":
            saw_ftyp = b"avif" in data[position + header_length:position + box_length]
        elif box_type == b"mdat" and box_length > header_length:
            saw_media_data = True
        position += box_length
    marker = data.find(b"ispe")
    if not saw_ftyp or not saw_media_data or marker < 4 or marker + 16 > len(data):
        return False
    property_length = int.from_bytes(data[marker - 4:marker], "big")
    if property_length < 20 or marker - 4 + property_length > len(data):
        return False
    width = int.from_bytes(data[marker + 8:marker + 12], "big")
    height = int.from_bytes(data[marker + 12:marker + 16], "big")
    return width > 0 and height > 0


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    position = 2
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            return None
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return None
        marker = data[position]
        position += 1
        if marker == 0xDA:
            return None
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            continue
        if position + 2 > len(data):
            return None
        length = int.from_bytes(data[position:position + 2], "big")
        if marker in start_of_frame and length >= 7:
            return (
                int.from_bytes(data[position + 5:position + 7], "big"),
                int.from_bytes(data[position + 3:position + 5], "big"),
            )
        position += length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    position = 12
    while position + 8 <= len(data):
        chunk_type = data[position:position + 4]
        length = int.from_bytes(data[position + 4:position + 8], "little")
        payload = data[position + 8:position + 8 + length]
        if chunk_type == b"VP8X" and length >= 10:
            return (
                int.from_bytes(payload[4:7], "little") + 1,
                int.from_bytes(payload[7:10], "little") + 1,
            )
        if chunk_type == b"VP8L" and length >= 5 and payload[0] == 0x2F:
            packed = int.from_bytes(payload[1:5], "little")
            return ((packed & 0x3FFF) + 1, ((packed >> 14) & 0x3FFF) + 1)
        if chunk_type == b"VP8 " and length >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            return (
                int.from_bytes(payload[6:8], "little") & 0x3FFF,
                int.from_bytes(payload[8:10], "little") & 0x3FFF,
            )
        position += 8 + length + (length & 1)
    return None


def _svg_dimensions(data: bytes) -> tuple[int, int] | None:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        return None
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError):
        return None
    if root.tag.rsplit("}", 1)[-1].casefold() != "svg":
        return None

    def numeric_dimension(value: str | None) -> float | None:
        if not value:
            return None
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:px|pt|pc|mm|cm|in)?\s*", value)
        return float(match.group(1)) if match else None

    width = numeric_dimension(root.get("width"))
    height = numeric_dimension(root.get("height"))
    if not width or not height:
        view_box = root.get("viewBox") or root.get("viewbox")
        if view_box:
            parts = re.split(r"[\s,]+", view_box.strip())
            try:
                if len(parts) == 4:
                    width, height = float(parts[2]), float(parts[3])
            except ValueError:
                return None
    if not width or not height or width <= 0 or height <= 0:
        return None
    return max(1, round(width)), max(1, round(height))


def image_dimensions(path: Path) -> tuple[int, int] | None:
    """Return dimensions only for a structurally complete supported image."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and _valid_png(data):
        return (
            int.from_bytes(data[16:20], "big"),
            int.from_bytes(data[20:24], "big"),
        )
    if data.startswith(b"\xff\xd8\xff") and _valid_jpeg(data):
        return _jpeg_dimensions(data)
    if data.startswith((b"GIF87a", b"GIF89a")) and _valid_gif(data):
        return (
            int.from_bytes(data[6:8], "little"),
            int.from_bytes(data[8:10], "little"),
        )
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and _valid_webp(data):
        return _webp_dimensions(data)
    if len(data) >= 12 and data[4:8] == b"ftyp" and b"avif" in data[8:32] and _valid_avif(data):
        marker = data.find(b"ispe")
        return (
            int.from_bytes(data[marker + 8:marker + 12], "big"),
            int.from_bytes(data[marker + 12:marker + 16], "big"),
        )
    if path.suffix.casefold() == ".svg" or data.lstrip().startswith(b"<"):
        return _svg_dimensions(data)
    return None


def image_looks_valid(path: Path, min_short_side: int = 1) -> bool:
    """Require a complete image whose width and height meet the requested floor."""
    dimensions = image_dimensions(path)
    return bool(dimensions and min(dimensions) >= min_short_side)


# Retain the validator's original private name for callers that predate the move.
_image_looks_valid = image_looks_valid


def slugify_brand_name(brand_name: str) -> str:
    """Return a stable ASCII filename slug for a brand name."""
    if not isinstance(brand_name, str):
        return ""
    normalized = unicodedata.normalize("NFKD", brand_name)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value)).strip("-")


def _resolve_public_http_target(url: str) -> tuple[str, urllib.parse.SplitResult, tuple[str, ...]]:
    """Validate a URL and return the exact public IPs approved for this hop."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")
    value = url.strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError(f"URL scheme is not allowed: {parsed.scheme or '(missing)'}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError as error:
        raise ValueError(f"URL has an invalid port: {error}") from error
    hostname = parsed.hostname.rstrip(".")
    if hostname.casefold() == "localhost" or hostname.casefold().endswith(".localhost"):
        raise ValueError("localhost URLs are not allowed")
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"URL hostname could not be resolved: {hostname}: {error}") from error
    addresses = tuple(dict.fromkeys(record[4][0] for record in resolved))
    if not addresses:
        raise ValueError(f"URL hostname resolved to no addresses: {hostname}")
    for address in addresses:
        try:
            parsed_address = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as error:
            raise ValueError(f"URL hostname resolved to an invalid address: {address}") from error
        if not parsed_address.is_global:
            raise ValueError(f"URL hostname resolves to a non-public address: {address}")
    return urllib.parse.urlunsplit(parsed), parsed, addresses


def validate_public_http_url(url: str) -> str:
    """Validate an HTTP(S) URL and resolve its host only to public addresses."""
    safe_url, _parsed, _addresses = _resolve_public_http_target(url)
    return safe_url


def resolve_public_http_url(value: str, base_url: str) -> str:
    return validate_public_http_url(urllib.parse.urljoin(base_url, value.strip()))


_GOOGLE_NEWS_ARTICLE_PATH_RE = re.compile(r"^/rss/articles/([^/?#]+)")
_EMBEDDED_HTTP_URL_RE = re.compile(
    rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+",
    flags=re.IGNORECASE,
)


def is_google_news_url(value: str) -> bool:
    """Return whether a URL points at the Google News host."""
    try:
        hostname = (urllib.parse.urlsplit(value.strip()).hostname or "").rstrip(".").casefold()
    except (AttributeError, ValueError):
        return False
    return hostname == "news.google.com"


def _is_google_owned_hostname(hostname: str) -> bool:
    hostname = hostname.rstrip(".").casefold()
    if re.search(r"(?:^|\.)google\.[a-z.]+$", hostname):
        return True
    infrastructure_domains = (
        "googleapis.com",
        "googleusercontent.com",
        "gstatic.com",
        "google-analytics.com",
        "googletagmanager.com",
        "googlesyndication.com",
        "googleadservices.com",
        "doubleclick.net",
    )
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in infrastructure_domains
    )


def _is_external_non_google_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except (AttributeError, ValueError):
        return False
    return (
        parsed.scheme.casefold() in {"http", "https"}
        and bool(parsed.hostname)
        and not _is_google_owned_hostname(parsed.hostname or "")
    )


def _decoded_google_news_targets(url: str) -> list[str]:
    match = _GOOGLE_NEWS_ARTICLE_PATH_RE.match(urllib.parse.urlsplit(url).path)
    if not match:
        return []
    segment = urllib.parse.unquote(match.group(1))
    try:
        padded = segment + "=" * (-len(segment) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError):
        return []
    return [match.group(0).decode("ascii") for match in _EMBEDDED_HTTP_URL_RE.finditer(decoded)]


def _validated_publisher_target(candidates: list[str]) -> str | None:
    asset_extensions = frozenset((
        ".js", ".mjs", ".css", ".json", ".xml", ".txt",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".woff", ".woff2",
    ))
    for candidate in candidates:
        candidate = html.unescape(candidate).strip()
        if not _is_external_non_google_url(candidate):
            continue
        parsed = urllib.parse.urlsplit(candidate)
        if any(parsed.path.casefold().endswith(ext) for ext in asset_extensions):
            continue
        try:
            return validate_public_http_url(candidate)
        except (ValueError, OSError):
            continue
    return None


def resolve_google_news_source_url(value: str, base_url: str = "") -> tuple[str, bool]:
    """Resolve a Google News RSS article wrapper to its safe publisher URL.

    The boolean is true only when the input was a Google News article URL whose
    publisher target could not be recovered. In that case the validated wrapper
    URL is retained so ingestion can flag, rather than silently discard, the item.
    """
    safe_url = resolve_public_http_url(value, base_url)
    parsed = urllib.parse.urlsplit(safe_url)
    if not is_google_news_url(safe_url) or not _GOOGLE_NEWS_ARTICLE_PATH_RE.match(parsed.path):
        return safe_url, False

    target = _validated_publisher_target(_decoded_google_news_targets(safe_url))
    if target:
        return target, False

    try:
        interstitial = fetch_text(safe_url)
        parser = GoogleNewsTargetExtractor()
        parser.feed(interstitial)
        parser.close()
        target = _validated_publisher_target(
            parser.attribute_targets + parser.external_hrefs
        )
    except Exception:
        target = None
    return (target, False) if target else (safe_url, True)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, pinned_ip: str, timeout: int) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = self._create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, pinned_ip: str, timeout: int) -> None:
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = self._create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address,
        )
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _request_path(parsed: urllib.parse.SplitResult) -> str:
    path = parsed.path or "/"
    return urllib.parse.urlunsplit(("", "", path, parsed.query, ""))


def _host_header(parsed: urllib.parse.SplitResult) -> str:
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    default_port = 443 if parsed.scheme.casefold() == "https" else 80
    return hostname if parsed.port in (None, default_port) else f"{hostname}:{parsed.port}"


def _open_pinned_response(
    parsed: urllib.parse.SplitResult,
    addresses: tuple[str, ...],
    timeout: int,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    last_error: Exception | None = None
    for address in addresses:
        connection_class = _PinnedHTTPSConnection if parsed.scheme.casefold() == "https" else _PinnedHTTPConnection
        connection = connection_class(parsed.hostname or "", port, address, timeout)
        try:
            connection.request(
                "GET", _request_path(parsed),
                headers={
                    "Host": _host_header(parsed),
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "close",
                },
            )
            return connection, connection.getresponse()
        except Exception as error:
            last_error = error
            connection.close()
    if last_error is not None:
        raise last_error
    raise RuntimeError("URL hostname resolved to no usable addresses")


def _read_bounded_response(
    response: http.client.HTTPResponse,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> bytes:
    raw_length = response.getheader("Content-Length")
    if raw_length is not None:
        try:
            content_length = int(raw_length)
        except ValueError as error:
            raise ValueError("response has an invalid Content-Length") from error
        if content_length < 0:
            raise ValueError("response has a negative Content-Length")
        if content_length > max_bytes:
            raise ValueError(f"response exceeds {max_bytes} byte limit")
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"response exceeds {max_bytes} byte limit")
    return payload


def fetch_bytes(
    url: str,
    timeout: int = FETCH_TIMEOUT,
    *,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_hosts: frozenset[str] | None = None,
    https_only: bool = False,
) -> tuple[bytes, str]:
    current_url = url
    redirect_statuses = {301, 302, 303, 307, 308}
    for redirect_count in range(MAX_REDIRECTS + 1):
        unresolved = urllib.parse.urlsplit(current_url)
        if https_only and unresolved.scheme.casefold() != "https":
            raise ValueError("HTTP response URL must use HTTPS")
        hostname = (unresolved.hostname or "").rstrip(".").casefold()
        if allowed_hosts is not None and hostname not in allowed_hosts:
            raise ValueError("HTTP response host is not allowlisted")
        safe_url, parsed, addresses = _resolve_public_http_target(current_url)
        connection, response = _open_pinned_response(parsed, addresses, timeout)
        try:
            if response.status in redirect_statuses:
                location = response.getheader("Location")
                if not location:
                    raise RuntimeError(f"HTTP {response.status} redirect has no Location header")
                if redirect_count >= MAX_REDIRECTS:
                    raise RuntimeError(f"too many redirects (limit {MAX_REDIRECTS})")
                current_url = urllib.parse.urljoin(safe_url, location)
                continue
            if response.status >= 400:
                raise RuntimeError(f"HTTP request failed with status {response.status}")
            payload = _read_bounded_response(response, max_bytes=max_bytes)
            return payload, response.headers.get_content_charset() or "utf-8"
        finally:
            response.close()
            connection.close()
    raise RuntimeError(f"too many redirects (limit {MAX_REDIRECTS})")


_WIKIPEDIA_API_HOSTS = frozenset({"en.wikipedia.org"})
_BRAND_LOGO_DOWNLOAD_HOSTS = frozenset({
    "en.wikipedia.org",
    "commons.wikimedia.org",
    "upload.wikimedia.org",
})


class _BrandLogoFetchError(RuntimeError):
    pass


def _brand_logo_warning(brand_name: str, reason: str) -> None:
    brand = re.sub(r"\s+", " ", brand_name).strip()[:120]
    brand = re.sub(r"https?://\S+", "[url]", brand, flags=re.IGNORECASE)
    print(f"brand logo fetch failed: {brand}: {reason}", file=sys.stderr)


def fetch_brand_logo(brand_name: str) -> Path | None:
    """Resolve a cached logo or fetch a bounded Wikipedia lead logo as PNG."""
    display_name = brand_name if isinstance(brand_name, str) else str(brand_name)
    try:
        clean_name = brand_name.strip() if isinstance(brand_name, str) else ""
        if not clean_name or len(clean_name) > 120 or any(ord(char) < 32 for char in clean_name):
            raise _BrandLogoFetchError("brand name must be 1-120 plain-text characters")
        slug = slugify_brand_name(clean_name)
        if not slug:
            raise _BrandLogoFetchError("brand name does not produce a safe slug")
        if len(slug) > 120:
            raise _BrandLogoFetchError("brand slug is too long")

        brands_dir = ROOT / "images" / "brands"
        for suffix in (".png", ".svg"):
            cached = brands_dir / f"{slug}{suffix}"
            if cached.is_file():
                return cached

        query = urllib.parse.urlencode({
            "action": "query",
            "titles": clean_name,
            "prop": "pageimages",
            "piprop": "original",
            "format": "json",
            "redirects": "1",
        })
        try:
            payload, charset = fetch_bytes(
                f"https://en.wikipedia.org/w/api.php?{query}",
                timeout=10,
                allowed_hosts=_WIKIPEDIA_API_HOSTS,
                https_only=True,
            )
        except Exception as error:
            raise _BrandLogoFetchError(
                f"Wikipedia API request failed ({type(error).__name__})"
            ) from error
        try:
            response = json.loads(payload.decode(charset))
            pages = response["query"]["pages"]
            page = next(
                item for item in pages.values()
                if isinstance(item, dict) and "missing" not in item
            )
            article_title = page["title"]
            original_url = page["original"]["source"]
        except (KeyError, StopIteration, TypeError, UnicodeError, json.JSONDecodeError) as error:
            raise _BrandLogoFetchError("Wikipedia returned no usable lead image") from error
        if not isinstance(article_title, str) or not isinstance(original_url, str):
            raise _BrandLogoFetchError("Wikipedia returned invalid image metadata")

        parsed_original = urllib.parse.urlsplit(original_url)
        original_host = (parsed_original.hostname or "").rstrip(".").casefold()
        if parsed_original.scheme.casefold() != "https" or original_host != "upload.wikimedia.org":
            raise _BrandLogoFetchError("Wikipedia image host is not allowlisted")
        filename = urllib.parse.unquote(Path(parsed_original.path).name)
        extension = Path(filename).suffix.casefold()
        title_matches = slugify_brand_name(article_title) == slug
        use_filepath_fallback = False
        if "logo" not in filename.casefold() and not (
            title_matches and extension in {".svg", ".png"}
        ):
            # Fallback: fetch the infobox from wikitext and look for a logo field
            try:
                wikitext_query = urllib.parse.urlencode({
                    "action": "query",
                    "titles": clean_name,
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    "format": "json",
                    "redirects": "1",
                })
                wikitext_payload, wikitext_charset = fetch_bytes(
                    f"https://en.wikipedia.org/w/api.php?{wikitext_query}",
                    timeout=10,
                    allowed_hosts=_WIKIPEDIA_API_HOSTS,
                    https_only=True,
                )
                wikitext_response = json.loads(wikitext_payload.decode(wikitext_charset))
                wikitext_pages = wikitext_response["query"]["pages"]
                wikitext_page = next(
                    item for item in wikitext_pages.values()
                    if isinstance(item, dict) and "missing" not in item
                )
                wikitext_content = wikitext_page["revisions"][0]["slots"]["main"]["*"]
                if not isinstance(wikitext_content, str):
                    raise _BrandLogoFetchError("Wikipedia returned no usable infobox logo")

                # Extract filename from infobox logo field; patterns: '| logo = File:Delta logo.svg', '|logo=Delta_logo.svg', 'logo_full', 'company_logo'
                logo_match = re.search(
                    r'\|\s*(?:logo(?:_full)?|company_logo)\s*=\s*(?:\[\[)?(?:File:|Image:)?\s*([^\[\n|]+)',
                    wikitext_content,
                    flags=re.IGNORECASE
                )
                if not logo_match:
                    raise _BrandLogoFetchError("Wikipedia infobox has no logo field")

                infobox_filename = logo_match.group(1).strip()
                # Remove brackets and size suffixes
                infobox_filename = re.sub(r'\[\[|\]\]', '', infobox_filename)
                infobox_filename = re.sub(r'\|.*$', '', infobox_filename).strip()

                # Extract first .svg/.png/.jpg filename
                logo_file_match = re.search(r'([^\s/]+\.(?:svg|png|jpg|jpeg))', infobox_filename, flags=re.IGNORECASE)
                if not logo_file_match:
                    raise _BrandLogoFetchError("Wikipedia infobox logo is not a recognized image format")

                filename = logo_file_match.group(1)
                extension = Path(filename).suffix.casefold()
                use_filepath_fallback = True
            except _BrandLogoFetchError:
                raise
            except Exception as error:
                raise _BrandLogoFetchError(
                    f"Wikipedia infobox lookup failed ({type(error).__name__})"
                ) from error

        # Construct download URL using Special:FilePath for SVG or infobox fallback
        if extension == ".svg" or use_filepath_fallback:
            quoted_filename = urllib.parse.quote(filename, safe="")
            download_url = (
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                f"{quoted_filename}?width=600"
            )
        else:
            download_url = original_url
        try:
            image_data, _charset = fetch_bytes(
                download_url,
                timeout=10,
                max_bytes=MAX_RESPONSE_BYTES,
                allowed_hosts=_BRAND_LOGO_DOWNLOAD_HOSTS,
                https_only=True,
            )
        except Exception as error:
            raise _BrandLogoFetchError(
                f"logo download failed ({type(error).__name__})"
            ) from error
        if len(image_data) > MAX_RESPONSE_BYTES:
            raise _BrandLogoFetchError("logo download exceeds 5MB")
        if not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise _BrandLogoFetchError("downloaded logo is not PNG")

        brands_dir.mkdir(parents=True, exist_ok=True)
        destination = brands_dir / f"{slug}.png"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{slug}.", suffix=".png", dir=brands_dir,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(image_data)
            if not image_looks_valid(temporary, min_short_side=200):
                raise _BrandLogoFetchError(
                    "downloaded logo is invalid or smaller than 200px"
                )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
    except _BrandLogoFetchError as error:
        _brand_logo_warning(display_name, str(error))
    except Exception as error:
        _brand_logo_warning(display_name, f"unexpected {type(error).__name__}")
    return None


def fetch_text(url: str, timeout: int = FETCH_TIMEOUT) -> str:
    payload, charset = fetch_bytes(url, timeout)
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def fetch_article_text(url: str, timeout: int = FETCH_TIMEOUT) -> str:
    return html_to_text(fetch_text(url, timeout))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def fill_template(template: str, slots: dict[str, str]) -> str:
    token_re = re.compile(r"{{([A-Z0-9_]+)}}")
    required = {match.group(1) for match in token_re.finditer(template)}
    missing = sorted(required - slots.keys())
    if missing:
        raise ValueError("unfilled prompt slots: " + ", ".join(missing))
    return token_re.sub(lambda match: slots[match.group(1)], template)


def parse_json_reply(raw: str) -> Any:
    """Accept strict JSON, tolerating only an accidental Markdown fence/preamble."""
    value = raw.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```\s*$", "", value)
    try:
        return json.loads(value)
    except json.JSONDecodeError as first_error:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", value):
            try:
                parsed, end = decoder.raw_decode(value[match.start():])
                if not value[match.start() + end:].strip().strip("`"):
                    return parsed
            except json.JSONDecodeError:
                continue
        raise first_error


CALCULATION_OPERATIONS = {"add", "subtract", "multiply", "divide"}


def _parse_calculation_quantity(value: Any) -> tuple[float, str]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("calculation values must be numbers or numeric strings")
    if isinstance(value, (int, float)):
        return float(value), "count"
    compact = re.sub(r"[\s,]", "", value).casefold().rstrip("+")
    percent = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)(?:%|percent)", compact)
    if percent:
        return float(percent.group(1)) / 100, "percent"
    cpp = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)(?:cpp|cpm|"
        r"¢(?:/(?:pt|point|mi|mile)|per(?:point|mile))?|"
        r"cents?per(?:point|mile))",
        compact,
    )
    if cpp:
        return float(cpp.group(1)) / 100, "cpp"
    quantity = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)(k)?(?:points?|pts?|miles?|mi)",
        compact,
    )
    if quantity:
        return float(quantity.group(1)) * (1000 if quantity.group(2) else 1), "points"
    multiplier = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)x", compact)
    if multiplier:
        return float(multiplier.group(1)), "points_per_dollar"
    plain = re.fullmatch(r"(\$?)([+-]?\d+(?:\.\d+)?)", compact)
    if plain:
        return float(plain.group(2)), "dollars" if plain.group(1) else "count"
    raise ValueError(f"unsupported calculation value: {value!r}")


def parse_calculation_value(value: Any) -> float:
    """Return the numeric magnitude; calculation validation also tracks its unit."""
    return _parse_calculation_quantity(value)[0]


def _multiply_units(left: str, right: str) -> str:
    if left == "count":
        return right
    if right == "count":
        return left
    if left == "percent":
        return right
    if right == "percent":
        return left
    if {left, right} == {"points", "cpp"}:
        return "dollars"
    if {left, right} == {"dollars", "points_per_dollar"}:
        return "points"
    raise ValueError(f"units do not compose for multiplication: {left} × {right}")


def _divide_units(numerator: str, denominator: str) -> str:
    if numerator == denominator:
        return "count"
    if denominator in {"count", "percent"}:
        return numerator
    if numerator == "dollars" and denominator == "cpp":
        return "points"
    if numerator == "dollars" and denominator == "points":
        return "cpp"
    if numerator == "points" and denominator == "dollars":
        return "points_per_dollar"
    if numerator == "points" and denominator == "points_per_dollar":
        return "dollars"
    raise ValueError(f"units do not compose for division: {numerator} ÷ {denominator}")


def _recompute_calculation_quantity(calculation: dict[str, Any]) -> tuple[float, str]:
    operation = calculation.get("operation")
    inputs = calculation.get("inputs")
    if operation not in CALCULATION_OPERATIONS:
        raise ValueError(f"unsupported calculation operation: {operation!r}")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("calculation inputs must be a non-empty list")
    quantities = [_parse_calculation_quantity(value) for value in inputs]
    if operation in {"subtract", "divide"} and len(quantities) != 2:
        raise ValueError(f"{operation} calculations require exactly two inputs")
    if operation in {"add", "subtract"}:
        units = {unit for _amount, unit in quantities}
        if len(units) != 1:
            rendered = ", ".join(unit for _amount, unit in quantities)
            raise ValueError(f"{operation} requires matching units, got: {rendered}")
        unit = quantities[0][1]
        if operation == "add":
            return sum(amount for amount, _unit in quantities), unit
        return quantities[0][0] - quantities[1][0], unit
    if operation == "multiply":
        amount, unit = quantities[0]
        for next_amount, next_unit in quantities[1:]:
            amount *= next_amount
            unit = _multiply_units(unit, next_unit)
        return amount, unit
    if quantities[1][0] == 0:
        raise ValueError("calculation division by zero")
    return quantities[0][0] / quantities[1][0], _divide_units(quantities[0][1], quantities[1][1])


def recompute_calculation(calculation: dict[str, Any]) -> float:
    return _recompute_calculation_quantity(calculation)[0]


def validate_calculations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("calculations must be a list")
    validated: list[dict[str, Any]] = []
    for index, calculation in enumerate(value):
        if not isinstance(calculation, dict):
            raise ValueError(f"calculation {index} must be an object")
        required = {"inputs", "operation", "result"}
        if required - calculation.keys():
            raise ValueError(f"calculation {index} is missing inputs, operation, or result")
        expected, expected_unit = _recompute_calculation_quantity(calculation)
        claimed, claimed_unit = _parse_calculation_quantity(calculation["result"])
        if expected_unit != claimed_unit and {expected_unit, claimed_unit} != {"count", "percent"}:
            raise ValueError(
                f"calculation {index} result unit does not match: expected {expected_unit}, got {claimed_unit}"
            )
        tolerance = max(1e-9, abs(expected) * 1e-6)
        if abs(expected - claimed) > tolerance:
            raise ValueError(
                f"calculation {index} result does not recompute: expected {expected:g}, got {claimed:g}"
            )
        validated.append(calculation)
    return validated


def run_codex(prompt: str, reasoning_effort: str, model: str = "gpt-5.6-sol") -> str:
    """Run Codex read-only and return only its final assistant message."""
    STATE.mkdir(parents=True, exist_ok=True)
    fd, output_name = tempfile.mkstemp(prefix="codex-last-", suffix=".txt")
    os.close(fd)
    output_path = Path(output_name)
    command = [
        "codex", "exec", "--ephemeral", "--color", "never",
        "--model", model,
        "--config", f'model_reasoning_effort="{reasoning_effort}"',
        "--sandbox", "read-only",
        "--cd", str(ROOT),
        "--output-last-message", str(output_path),
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"codex exec failed with exit {result.returncode}: {detail[-2000:]}")
        reply = output_path.read_text(encoding="utf-8").strip()
        if not reply:
            raise RuntimeError("codex exec produced no final message")
        return reply
    finally:
        output_path.unlink(missing_ok=True)


def compact_card(card: dict[str, Any]) -> dict[str, Any]:
    fields = ("id", "name", "annual_fee", "welcome_bonus", "features", "card_url", "practical_advice")
    return {field: card.get(field) for field in fields}


def card_url(card: dict[str, Any]) -> str:
    value = str(card.get("card_url", ""))
    if value.startswith(("http://", "https://", "/")):
        return value
    return "/" + value.lstrip("/")


def canonical_card_source_url(card: dict[str, Any]) -> str:
    value = card_url(card)
    if value.startswith(("http://", "https://")):
        return value
    return "https://practicalrewards.com/" + value.lstrip("/")
