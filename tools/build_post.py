#!/usr/bin/env python3
"""Compile a validated draft into the static blog, sitemap, feed, and state."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import (
    ROOT, STATE, card_mentions, card_url, read_json, validate_calculations,
    validate_content_html, write_json,
)


TOKEN_RE = re.compile(r"{{([A-Z0-9_]+)}}")
IMAGE_ERROR_HANDLER = (
    "this.setAttribute('visibility','hidden');"
    "this.previousElementSibling.setAttribute('visibility','visible')"
)


class CardLinkifier(HTMLParser):
    """Preserve article HTML and link the first unlinked mention per card."""

    def __init__(self, cards: list[dict[str, Any]]) -> None:
        super().__init__(convert_charrefs=False)
        self.cards = cards
        self.linked: set[int] = set()
        self.anchor_depth = 0
        self.output: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self.anchor_depth += 1
        self.output.append(self.get_starttag_text())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        self.output.append(f"</{tag}>")
        if tag.lower() == "a" and self.anchor_depth:
            self.anchor_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.anchor_depth:
            self.output.append(data)
            return
        remaining = data
        while remaining:
            mentions = [
                mention for mention in card_mentions(remaining, self.cards)
                if int(mention[2]["id"]) not in self.linked
            ]
            if not mentions:
                self.output.append(remaining)
                break
            start, end, card, _alias = min(
                mentions,
                key=lambda mention: (mention[0], -(mention[1] - mention[0])),
            )
            self.output.append(remaining[:start])
            visible = remaining[start:end]
            self.output.append(
                f'<a href="{html.escape(card_url(card), quote=True)}">{visible}</a>'
            )
            self.linked.add(int(card["id"]))
            remaining = remaining[end:]

    def handle_entityref(self, name: str) -> None:
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.output.append(f"<!{decl}>")

    def unknown_decl(self, data: str) -> None:
        self.output.append(f"<![{data}]>")


def linkify_cards(content: str, cards: list[dict[str, Any]]) -> str:
    parser = CardLinkifier(cards)
    parser.feed(content)
    parser.close()
    return "".join(parser.output)


def fill_post_template(template: str, values: dict[str, str]) -> str:
    required = {match.group(1) for match in TOKEN_RE.finditer(template)}
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError("unfilled post template tokens: " + ", ".join(missing))
    return TOKEN_RE.sub(lambda match: values[match.group(1)], template)


def _hero_label_lines(label: str, limit: int = 36) -> list[str]:
    words = label.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) <= 2:
        return lines
    second = " ".join(lines[1:])
    if len(second) > limit:
        second = second[:limit - 1].rstrip() + "…"
    return [lines[0], second]


def _image_looks_valid(path: Path) -> bool:
    """Require a structurally complete supported image with nonzero dimensions."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _valid_png(data)
    if data.startswith(b"\xff\xd8\xff"):
        return _valid_jpeg(data)
    if data.startswith((b"GIF87a", b"GIF89a")):
        return _valid_gif(data)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return _valid_webp(data)
    if len(data) >= 12 and data[4:8] == b"ftyp" and b"avif" in data[8:32]:
        return _valid_avif(data)
    return False


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


def _local_image_href(relative: str, base: Path, root: Path) -> str | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    if not candidate.is_file() or not _image_looks_valid(candidate):
        return None
    return "/" + relative


def _card_art_href(card: dict[str, Any] | None, root: Path = ROOT) -> str | None:
    if not card:
        return None
    image_url = card.get("image_url")
    if not isinstance(image_url, str) or not image_url.strip():
        return None
    relative = image_url.strip().lstrip("/")
    if not relative.startswith("images/"):
        return None
    return _local_image_href(relative, root / "images", root)


def _brand_art_href(asset: Any, root: Path = ROOT) -> str | None:
    if not isinstance(asset, str) or not asset.strip():
        return None
    filename = asset.strip()
    if Path(filename).name != filename:
        return None
    relative = f"images/brands/{filename}"
    return _local_image_href(relative, root / "images" / "brands", root)


def _typographic_art() -> str:
    return (
        '        <g class="pr-hero-art pr-hero-art-fallback" aria-hidden="true">\n'
        '            <circle cx="615" cy="210" r="72" fill="#ffffff" fill-opacity="0.06"/>\n'
        '            <text x="615" y="225" text-anchor="middle" fill="#d1fae5" fill-opacity="0.82" '
        'font-family="Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif" font-size="48" font-weight="900">PR</text>\n'
        '        </g>\n'
    )


def _hidden_typographic_fallback(indent: str) -> str:
    return (
        f'{indent}<g class="pr-hero-art-fallback" visibility="hidden" aria-hidden="true">\n'
        f'{indent}    <text x="615" y="225" text-anchor="middle" fill="#d1fae5" fill-opacity="0.82" '
        'font-family="Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif" font-size="48" font-weight="900">PR</text>\n'
        f'{indent}</g>\n'
    )


def render_hero(
    draft: dict[str, Any],
    cards: list[dict[str, Any]],
    root: Path = ROOT,
) -> str:
    hero = draft.get("hero")
    if isinstance(hero, dict):
        kicker = str(hero.get("kicker", "PRACTICAL REWARDS")).strip()
        stat = str(hero.get("stat", "HONEST MATH")).strip()
        label = str(hero.get("label", draft.get("title", "Straight answers, useful math"))).strip()
        art_spec = hero.get("art")
        if not isinstance(art_spec, dict) and "card_id" in hero:
            # Keep old drafts buildable while all new drafts use the nested art contract.
            art_spec = {"type": "card", "card_id": hero.get("card_id")}
    else:
        kicker = "PRACTICAL REWARDS"
        stat = "HONEST MATH"
        label = str(draft.get("title", "Straight answers, useful math")).strip()
        if len(label) >= 80:
            label = label[:78].rstrip() + "…"
        art_spec = {"type": "none"}

    kicker_xml = html.escape(kicker)
    stat_xml = html.escape(stat)
    label_lines = _hero_label_lines(label)
    label_tspans = "".join(
        f'<tspan x="60" dy="{0 if index == 0 else 30}">{html.escape(line)}</tspan>'
        for index, line in enumerate(label_lines)
    )
    stat_size = 110 if len(stat) <= 8 else (88 if len(stat) <= 12 else 70)
    art = ""
    art_type = art_spec.get("type") if isinstance(art_spec, dict) else None
    if art_type == "card":
        card_id = art_spec.get("card_id")
        card = next((item for item in cards if item.get("id") == card_id), None)
        art_href = _card_art_href(card, root)
        if art_href:
            art = (
                '        <g clip-path="url(#pr-hero-art-window)">\n'
                '            <g class="pr-hero-art pr-hero-art-card" filter="url(#pr-hero-card-shadow)" transform="rotate(-8 610 210)">\n'
                '                <rect x="485" y="131" width="250" height="157" rx="14" fill="#ffffff" fill-opacity="0.08"/>\n'
                f'{_hidden_typographic_fallback("                ")}'
                f'                <image href="{html.escape(art_href, quote=True)}" x="485" y="131" width="250" height="157" '
                f'preserveAspectRatio="xMidYMid meet" clip-path="url(#pr-hero-card-clip)" onerror="{IMAGE_ERROR_HANDLER}"/>\n'
                '            </g>\n'
                '        </g>\n'
            )
        else:
            art = _typographic_art()
    elif art_type == "brand":
        art_href = _brand_art_href(art_spec.get("asset"), root)
        if art_href:
            art = (
                '        <g class="pr-hero-art pr-hero-art-brand" aria-hidden="true">\n'
                '            <circle cx="615" cy="210" r="72" fill="#ffffff" fill-opacity="0.06"/>\n'
                f'{_hidden_typographic_fallback("            ")}'
                f'            <image href="{html.escape(art_href, quote=True)}" x="555" y="150" width="120" height="120" '
                f'preserveAspectRatio="xMidYMid meet" onerror="{IMAGE_ERROR_HANDLER}"/>\n'
                '        </g>\n'
            )
        else:
            art = _typographic_art()
    elif art_type not in {None, "none"}:
        art = _typographic_art()

    aria_label = html.escape(f"{kicker}: {stat}. {label}", quote=True)
    return (
        '<div class="pr-hero">\n'
        '    <svg class="pr-hero-ground" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">\n'
        '        <defs>\n'
        '            <linearGradient id="pr-hero-ground-gradient" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '                <stop offset="0%" stop-color="#0f2027"/>\n'
        '                <stop offset="30%" stop-color="#0f2027"/>\n'
        '                <stop offset="70%" stop-color="#203a43"/>\n'
        '                <stop offset="100%" stop-color="#2c5364"/>\n'
        '            </linearGradient>\n'
        '        </defs>\n'
        '        <rect width="100" height="100" fill="url(#pr-hero-ground-gradient)"/>\n'
        '    </svg>\n'
        '    <div class="pr-hero-inner">\n'
        f'        <svg class="pr-hero-content" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" preserveAspectRatio="xMinYMid slice" role="img" aria-label="{aria_label}">\n'
        '        <defs>\n'
        '            <linearGradient id="pr-hero-accent" x1="0" y1="48" x2="0" y2="372" gradientUnits="userSpaceOnUse">\n'
        '                <stop offset="0%" stop-color="#059669"/>\n'
        '                <stop offset="100%" stop-color="#22c55e"/>\n'
        '            </linearGradient>\n'
        '            <filter id="pr-hero-card-shadow" x="-30%" y="-40%" width="170%" height="190%">\n'
        '                <feDropShadow dx="0" dy="18" stdDeviation="16" flood-color="#000000" flood-opacity="0.38"/>\n'
        '            </filter>\n'
        '            <clipPath id="pr-hero-card-clip"><rect x="485" y="131" width="250" height="157" rx="14"/></clipPath>\n'
        '            <clipPath id="pr-hero-art-window"><rect x="470" y="0" width="290" height="420"/></clipPath>\n'
        '        </defs>\n'
        '        <path d="M38 52H445M38 210H445M38 368H445" fill="none" stroke="#ffffff" stroke-opacity="0.055" stroke-width="2"/>\n'
        '        <rect x="28" y="48" width="7" height="324" rx="3.5" fill="url(#pr-hero-accent)"/>\n'
        f'        <text x="60" y="104" fill="#34d399" font-family="Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif" font-size="20" font-weight="800" letter-spacing="3">{kicker_xml}</text>\n'
        f'        <text x="54" y="232" fill="#ffffff" font-family="Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif" font-size="{stat_size}" font-weight="900" letter-spacing="-3">{stat_xml}</text>\n'
        f'        <text y="292" fill="#e7e5e4" font-family="Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif" font-size="24" font-weight="500">{label_tspans}</text>\n'
        f'{art}'
        '        </svg>\n'
        '    </div>\n'
        '</div>'
    )


def slug_collision_reasons(
    slug: str,
    published: list[dict[str, Any]],
    root: Path = ROOT,
) -> list[str]:
    reasons: list[str] = []
    if any(isinstance(item, dict) and str(item.get("slug", "")) == slug for item in published):
        reasons.append("published.json record")
    if (root / "blog" / f"{slug}.html").exists():
        reasons.append("existing blog page")
    checks = (
        (root / "blog" / "index.html", f"POST:{slug}:BEGIN", "blog index entry"),
        (root / "sitemap.xml", f"/blog/{slug}.html", "sitemap entry"),
        (root / "blog" / "feed.xml", f"/blog/{slug}.html", "feed entry"),
    )
    for path, marker, label in checks:
        if path.exists() and marker in path.read_text(encoding="utf-8"):
            reasons.append(label)
    return reasons


def post_card(draft: dict[str, Any], date_display: str) -> str:
    slug = draft["slug"]
    return (
        f'            <!-- POST:{slug}:BEGIN -->\n'
        f'            <article class="post-card">\n'
        f'                <h3><a href="/blog/{html.escape(slug, quote=True)}.html">'
        f'{html.escape(draft["title"])}</a></h3>\n'
        f'                <p class="post-date"><time datetime="{dt.date.today().isoformat()}">'
        f'{html.escape(date_display)}</time></p>\n'
        f'                <p>{html.escape(draft["meta_description"])}</p>\n'
        f'            </article>\n'
        f'            <!-- POST:{slug}:END -->\n'
    )


def update_blog_index(draft: dict[str, Any], date_display: str) -> None:
    path = ROOT / "blog" / "index.html"
    value = path.read_text(encoding="utf-8")
    begin = "<!-- POSTS:BEGIN -->"
    if begin not in value or "<!-- POSTS:END -->" not in value:
        raise ValueError("blog/index.html is missing post insertion markers")
    slug = re.escape(str(draft["slug"]))
    value = re.sub(
        rf"\s*<!-- POST:{slug}:BEGIN -->.*?<!-- POST:{slug}:END -->\s*",
        "\n",
        value,
        flags=re.DOTALL,
    )
    value = re.sub(
        r"\s*<p\s+class=[\"']posts-placeholder[\"'][^>]*>\s*First posts are on the way\.\s*</p>\s*",
        "\n",
        value,
        flags=re.IGNORECASE,
    )
    value = value.replace(begin, begin + "\n" + post_card(draft, date_display), 1)
    path.write_text(value, encoding="utf-8")


def update_sitemap(slug: str, today: str) -> None:
    path = ROOT / "sitemap.xml"
    value = path.read_text(encoding="utf-8")
    loc = f"https://practicalrewards.com/blog/{slug}.html"
    escaped_loc = re.escape(loc)
    value = re.sub(
        rf"\s*<url>\s*<loc>{escaped_loc}</loc>.*?</url>\s*",
        "\n",
        value,
        flags=re.DOTALL,
    )
    entry = (
        "  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.6</priority>\n"
        "  </url>\n"
    )
    if "</urlset>" not in value:
        raise ValueError("sitemap.xml has no closing urlset element")
    value = value.replace("</urlset>", entry + "</urlset>", 1)
    path.write_text(value, encoding="utf-8")


def page_description(slug: str, fallback: str) -> str:
    path = ROOT / "blog" / f"{slug}.html"
    if not path.exists():
        return fallback
    value = path.read_text(encoding="utf-8")
    match = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
        value,
        flags=re.IGNORECASE,
    )
    return html.unescape(match.group(1)) if match else fallback


def rss_date(iso_date: str) -> str:
    parsed = dt.date.fromisoformat(iso_date)
    moment = dt.datetime.combine(parsed, dt.time(12), tzinfo=dt.timezone.utc)
    return email.utils.format_datetime(moment)


def regenerate_feed(published: list[dict[str, Any]]) -> None:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Practical Rewards Blog"
    ET.SubElement(channel, "link").text = "https://practicalrewards.com/blog/"
    ET.SubElement(channel, "description").text = (
        "Straight answers about credit cards, points, cash back, and the fine print."
    )
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(dt.datetime.now(dt.timezone.utc))
    newest = sorted(
        (item for item in published if isinstance(item, dict) and item.get("date") and item.get("slug")),
        key=lambda item: (str(item["date"]), str(item["slug"])),
        reverse=True,
    )[:20]
    for record in newest:
        slug = str(record["slug"])
        link = f"https://practicalrewards.com/blog/{slug}.html"
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(record.get("title", slug))
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = link
        ET.SubElement(item, "pubDate").text = rss_date(str(record["date"]))
        ET.SubElement(item, "description").text = page_description(slug, str(record.get("title", slug)))
    ET.indent(rss, space="  ")
    tree = ET.ElementTree(rss)
    tree.write(ROOT / "blog" / "feed.xml", encoding="utf-8", xml_declaration=True)


def build_post() -> Path:
    draft = read_json(STATE / "draft.json")
    if not isinstance(draft, dict):
        raise ValueError("tools/state/draft.json is missing or invalid")
    required = {
        "title", "meta_description", "slug", "content_html", "sources",
        "cards_mentioned", "calculations",
    }
    if required - draft.keys():
        raise ValueError("draft.json is missing required fields")
    slug = str(draft["slug"])
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("draft slug is unsafe")
    validate_content_html(str(draft["content_html"]))
    validate_calculations(draft["calculations"])

    sources = draft["sources"]
    if not isinstance(sources, list) or not all(isinstance(source, dict) for source in sources):
        raise ValueError("draft sources must be a list of source objects")
    published_path = STATE / "published.json"
    published = read_json(published_path, [])
    if not isinstance(published, list):
        raise ValueError("published.json must contain a list")
    collisions = slug_collision_reasons(slug, published)
    if collisions:
        raise ValueError(f"refusing to overwrite slug {slug}: " + ", ".join(collisions))

    cards = read_json(ROOT / "cards.json", [])
    card_ids = set(draft.get("cards_mentioned", []))
    selected_cards = [card for card in cards if card.get("id") in card_ids]
    if len(selected_cards) != len(card_ids):
        raise ValueError("draft references an unknown card ID")
    content = linkify_cards(str(draft["content_html"]), selected_cards)
    today = dt.date.today()
    iso_date = today.isoformat()
    display_date = today.strftime("%B %d, %Y").replace(" 0", " ")
    canonical = f"https://practicalrewards.com/blog/{slug}.html"
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": str(draft["title"])[:110],
        "author": {"@type": "Person", "name": "Carter", "url": "https://practicalrewards.com/about.html"},
        "publisher": {"@type": "Organization", "name": "Practical Rewards", "url": "https://practicalrewards.com"},
        "datePublished": iso_date,
        "dateModified": iso_date,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    }
    template = (ROOT / "blog" / "post-template.html").read_text(encoding="utf-8")
    page = fill_post_template(template, {
        "TITLE": html.escape(str(draft["title"])),
        "META_DESCRIPTION": html.escape(str(draft["meta_description"]), quote=True),
        "CANONICAL_URL": canonical,
        "DATE_PUBLISHED": iso_date,
        "DATE_MODIFIED": iso_date,
        "DATE_DISPLAY": display_date,
        "JSON_LD": json.dumps(json_ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
        "HERO": render_hero(draft, selected_cards),
        "CONTENT": content,
    })
    output_path = ROOT / "blog" / f"{slug}.html"
    output_path.write_text(page, encoding="utf-8")
    update_blog_index(draft, display_date)
    update_sitemap(slug, iso_date)

    brief = read_json(STATE / "todays-brief.json", {})
    post_type = brief.get("type", "evergreen") if isinstance(brief, dict) else "evergreen"
    record = {"slug": slug, "title": str(draft["title"]), "date": iso_date, "type": post_type}
    published.append(record)
    regenerate_feed(published)
    write_json(published_path, published)
    print(f"Built {output_path}")
    return output_path


def main() -> int:
    build_post()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
