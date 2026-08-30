#!/usr/bin/env python3
"""Compile a validated draft into the static blog, sitemap, feed, and state."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import (
    ROOT, STATE, card_mentions, card_url, read_json, validate_calculations,
    validate_content_html, validate_public_http_url, write_json,
)


TOKEN_RE = re.compile(r"{{([A-Z0-9_]+)}}")


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


def render_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return ""
    items: list[str] = []
    for source in sources:
        url = validate_public_http_url(str(source.get("url", "")))
        label = str(source.get("claim_hint", "")).strip()
        if not label:
            raise ValueError("every source requires a non-empty claim_hint")
        items.append(f'<li><a href="{html.escape(url, quote=True)}">{html.escape(label)}</a></li>')
    return "<h2>Sources</h2>\n<ul>\n" + "\n".join(items) + "\n</ul>"


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
        "author": {"@type": "Organization", "name": "Practical Rewards", "url": "https://practicalrewards.com"},
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
        "CONTENT": content,
        "SOURCES": render_sources(sources),
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
