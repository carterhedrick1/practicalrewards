#!/usr/bin/env python3
"""Draft a Practical Rewards post as validated strict JSON."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from common import (
    ROOT, STATE, TOOLS, canonical_card_source_url, card_mentions,
    card_product_aliases, compact_card, fetch_article_text, fill_template,
    html_to_text, is_google_news_url, issuer_aliases, normalize_card_text,
    normalized_phrase_in_text, parse_json_reply, read_json, run_codex,
    slugify_brand_name, unambiguous_card_aliases, validate_calculations,
    validate_content_html, validate_public_http_url, write_json,
)


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLAIN_TEXT_MARKUP_RE = re.compile(
    r"<[^>]*>|&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]+);",
    re.IGNORECASE,
)
DRAFT_SOURCES_UNAVAILABLE = "DRAFT_SOURCES_UNAVAILABLE"


def fetch_source_articles(urls: list[str]) -> list[dict[str, str]]:
    try:
        cached = read_json(STATE / "articles.json", {})
    except (OSError, ValueError):
        cached = {}
    if not isinstance(cached, dict):
        cached = {}
    articles: list[dict[str, str]] = []
    for url in urls:
        cached_text = cached.get(url)
        if isinstance(cached_text, str) and cached_text.strip():
            articles.append({"url": url, "text": cached_text})
            continue
        try:
            text = fetch_article_text(url, timeout=15)
            if not text:
                raise RuntimeError("no readable page text")
            articles.append({"url": url, "text": text})
        except Exception as error:
            print(f"WARNING: draft source unavailable {url}: {error}", file=sys.stderr)
    if urls and not articles:
        print(DRAFT_SOURCES_UNAVAILABLE, file=sys.stderr)
        raise RuntimeError("no draft source articles were available")
    write_json(STATE / "articles.json", {
        article["url"]: article["text"] for article in articles
    })
    return articles


def available_brand_assets(root: Path = ROOT) -> list[str]:
    brands_dir = root / "images" / "brands"
    if not brands_dir.is_dir():
        return []
    return sorted(path.name for path in brands_dir.iterdir() if path.is_file())


def _downgrade_hero_art(reason: str) -> dict[str, str]:
    print(f"Note: {reason}; using hero.art type none", file=sys.stderr)
    return {"type": "none"}


def validate_hero(
    value: Any,
    allowed_card_ids: set[int],
    listed_card_ids: set[int],
    root: Path = ROOT,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("hero must be an object when present")
    allowed_keys = {"kicker", "stat", "label", "art"}
    unexpected = sorted(value.keys() - allowed_keys)
    if unexpected:
        raise ValueError("hero contains unexpected keys: " + ", ".join(unexpected))
    missing = {"kicker", "stat", "label"} - value.keys()
    if missing:
        raise ValueError("hero is missing keys: " + ", ".join(sorted(missing)))
    for field in ("kicker", "stat", "label"):
        field_value = value[field]
        if not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(f"hero.{field} must be a non-empty string")
        if PLAIN_TEXT_MARKUP_RE.search(field_value):
            raise ValueError(f"hero.{field} must be plain text without markup")
        value[field] = field_value.strip()
    if len(value["kicker"]) >= 28:
        raise ValueError("hero.kicker must be under 28 characters")
    if len(value["label"]) >= 80:
        raise ValueError("hero.label must be under 80 characters")
    art = value.get("art")
    if not isinstance(art, dict):
        value["art"] = _downgrade_hero_art("hero.art must be an object")
        return value
    art_type = art.get("type")
    if art_type == "card":
        card_id = art.get("card_id")
        if set(art) != {"type", "card_id"}:
            value["art"] = _downgrade_hero_art("card art must contain only type and card_id")
        elif not isinstance(card_id, int) or isinstance(card_id, bool):
            value["art"] = _downgrade_hero_art("hero.art.card_id must be an integer")
        elif card_id not in allowed_card_ids:
            value["art"] = _downgrade_hero_art("hero.art.card_id is outside the supplied card slice")
        elif card_id not in listed_card_ids:
            value["art"] = _downgrade_hero_art("hero.art.card_id is not in cards_mentioned")
    elif art_type == "brand":
        if set(art) == {"type", "asset"}:
            asset = art.get("asset")
            available = set(available_brand_assets(root))
            if not isinstance(asset, str) or asset not in available:
                value["art"] = _downgrade_hero_art(
                    "hero.art.asset is not available in images/brands"
                )
        elif set(art) == {"type", "brand_name"}:
            brand_name = art.get("brand_name")
            if (
                not isinstance(brand_name, str)
                or not brand_name.strip()
                or len(brand_name.strip()) > 120
                or any(ord(character) < 32 for character in brand_name.strip())
                or PLAIN_TEXT_MARKUP_RE.search(brand_name)
                or not slugify_brand_name(brand_name)
                or len(slugify_brand_name(brand_name)) > 120
            ):
                value["art"] = _downgrade_hero_art(
                    "hero.art.brand_name must be a plain brand name with a safe slug"
                )
            else:
                art["brand_name"] = brand_name.strip()
        else:
            value["art"] = _downgrade_hero_art(
                "brand art must contain type plus asset or brand_name"
            )
    elif art_type == "none":
        if set(art) != {"type"}:
            value["art"] = _downgrade_hero_art("none art must contain only type")
    else:
        value["art"] = _downgrade_hero_art("hero.art.type must be card, brand, or none")
    return value


def validate_citable_source_url(url: str) -> str:
    if is_google_news_url(url):
        raise ValueError("Google News wrapper URLs cannot be cited as sources")
    return validate_public_http_url(url)


def news_cards(cards: list[dict[str, Any]], haystack: str) -> list[dict[str, Any]]:
    normalized = normalize_card_text(haystack)
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, card in enumerate(cards):
        matched_aliases = {
            alias for alias in unambiguous_card_aliases(card, cards)
            if normalized_phrase_in_text(alias, normalized)
        }
        issuer_hit = any(
            normalized_phrase_in_text(alias, normalized)
            for alias in issuer_aliases(card)
        )
        product_hit = any(
            normalized_phrase_in_text(alias, normalized)
            for alias in card_product_aliases(card, include_single=True)
        )
        issuer_product_hit = issuer_hit and product_hit
        if matched_aliases or issuer_product_hit:
            longest = max((len(alias.split()) for alias in matched_aliases), default=0)
            score = longest * 20 + (15 if issuer_product_hit else 0)
            ranked.append((score, -index, card))
    ranked.sort(reverse=True, key=lambda row: (row[0], row[1]))
    return [card for _, _, card in ranked[:8]]


def validate_draft(
    value: Any,
    allowed_card_ids: set[int],
    allowed_source_urls: set[str],
    expected_slug: str | None,
    forbidden_slugs: set[str] | None = None,
    required_source_urls: set[str] | None = None,
    cards_all: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("draft reply must be a JSON object")
    required = {
        "title", "meta_description", "slug", "content_html", "sources",
        "cards_mentioned", "calculations",
    }
    missing = required - value.keys()
    if missing:
        raise ValueError("draft is missing keys: " + ", ".join(sorted(missing)))
    for field in ("title", "meta_description", "slug", "content_html"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if len(value["title"]) > 110 or "!" in value["title"]:
        raise ValueError("title must be at most 110 characters and contain no exclamation point")
    if not SLUG_RE.fullmatch(value["slug"]):
        raise ValueError("slug must contain only lowercase letters, numbers, and hyphens")
    if expected_slug and value["slug"] != expected_slug:
        raise ValueError(f"evergreen slug must be {expected_slug}")
    if value["slug"] in (forbidden_slugs or set()):
        raise ValueError(f"slug is already published or has an existing page: {value['slug']}")
    validate_content_html(value["content_html"])
    if not isinstance(value["sources"], list) or not all(
        isinstance(source, dict)
        and isinstance(source.get("claim_hint"), str)
        and bool(source["claim_hint"].strip())
        and isinstance(source.get("url"), str)
        and source["url"].startswith(("http://", "https://"))
        for source in value["sources"]
    ):
        raise ValueError("sources must be a list of claim_hint/url objects")
    for source in value["sources"]:
        validate_citable_source_url(source["url"])
    returned_urls = {str(source["url"]) for source in value["sources"]}
    unexpected_urls = sorted(returned_urls - allowed_source_urls)
    if unexpected_urls:
        raise ValueError("sources contain URLs outside the supplied fact packet: " + ", ".join(unexpected_urls))
    missing_urls = sorted((required_source_urls or set()) - returned_urls)
    if missing_urls:
        raise ValueError("draft omitted required source citations: " + ", ".join(missing_urls))
    if not isinstance(value["cards_mentioned"], list) or not all(
        isinstance(card_id, int) and card_id in allowed_card_ids for card_id in value["cards_mentioned"]
    ):
        raise ValueError("cards_mentioned contains an ID outside the supplied card slice")
    value["cards_mentioned"] = list(dict.fromkeys(value["cards_mentioned"]))
    listed_ids = set(value["cards_mentioned"])
    if "hero" in value:
        value["hero"] = validate_hero(value["hero"], allowed_card_ids, listed_ids)
    if cards_all is not None:
        content_ids = {
            int(mention[2]["id"])
            for mention in card_mentions(html_to_text(value["content_html"]), cards_all)
        }
        outside = sorted(content_ids - allowed_card_ids)
        if outside:
            raise ValueError("content_html mentions card IDs outside the supplied card slice: " + ", ".join(map(str, outside)))
        omitted = sorted(content_ids - listed_ids)
        if omitted:
            raise ValueError("content_html mentions card IDs omitted from cards_mentioned: " + ", ".join(map(str, omitted)))
        cards_by_id = {int(card["id"]): card for card in cards_all if isinstance(card.get("id"), int)}
        required_card_urls = {
            canonical_card_source_url(cards_by_id[card_id])
            for card_id in listed_ids
            if card_id in cards_by_id
        }
        missing_card_urls = sorted(required_card_urls - returned_urls)
        if missing_card_urls:
            raise ValueError("draft omitted required card-page citation(s): " + ", ".join(missing_card_urls))
    value["calculations"] = validate_calculations(value["calculations"])
    return value


def existing_slugs() -> set[str]:
    published = read_json(STATE / "published.json", [])
    if not isinstance(published, list):
        raise ValueError("tools/state/published.json must contain a JSON list")
    slugs = {
        str(item.get("slug"))
        for item in published
        if isinstance(item, dict) and item.get("slug")
    }
    slugs.update(path.stem for path in (ROOT / "blog").glob("*.html"))
    return slugs


def revision_context() -> tuple[dict[str, Any], list[str]]:
    draft_path = STATE / "draft.json"
    if not draft_path.is_file():
        raise ValueError("revise mode requires tools/state/draft.json, but it is missing")
    try:
        previous_draft = read_json(draft_path)
    except (OSError, ValueError) as error:
        raise ValueError(f"revise mode requires a valid tools/state/draft.json: {error}") from error
    if not isinstance(previous_draft, dict):
        raise ValueError("revise mode requires a valid tools/state/draft.json object")
    slug = previous_draft.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError("revise mode requires draft.json to contain a valid slug")
    report_path = STATE / "verify-report.json"
    if not report_path.is_file():
        raise ValueError("revise mode requires tools/state/verify-report.json, but it is missing")
    try:
        report = read_json(report_path)
    except (OSError, ValueError) as error:
        raise ValueError(f"revise mode requires a valid tools/state/verify-report.json: {error}") from error
    if not isinstance(report, dict):
        raise ValueError("revise mode requires a valid tools/state/verify-report.json object")
    failures = report.get("failures")
    if not isinstance(failures, list) or not all(isinstance(failure, str) for failure in failures):
        raise ValueError("revise mode requires verify-report.json failures to be a list of strings")
    return previous_draft, failures


def draft() -> dict[str, Any]:
    revise = os.environ.get("DRAFT_REVISE") == "1"
    previous_draft, verification_failures = revision_context() if revise else ({}, [])
    brief = read_json(STATE / "todays-brief.json")
    if not isinstance(brief, dict) or brief.get("type") not in {"evergreen", "news"}:
        raise ValueError("todays-brief.json is missing or invalid")
    style = (TOOLS / "content" / "style-guide.md").read_text(encoding="utf-8")
    cards = read_json(ROOT / "cards.json", [])
    if not isinstance(cards, list):
        raise ValueError("cards.json must contain a list")

    slots = {
        "STYLE_GUIDE": style,
        "BRIEF_JSON": json.dumps(brief, ensure_ascii=False, indent=2),
        "BRAND_ASSETS_JSON": json.dumps(available_brand_assets(), ensure_ascii=False),
    }
    forbidden_slugs = existing_slugs()
    required_source_urls: set[str] = set()
    expected_slug: str | None = None
    if brief["type"] == "evergreen":
        topic_map = read_json(TOOLS / "content" / "topic-map.json", {})
        topics = topic_map.get("topics", []) if isinstance(topic_map, dict) else []
        topic = next((item for item in topics if item.get("slug") == brief.get("slug")), None)
        if topic is None:
            raise ValueError(f"unknown evergreen topic slug: {brief.get('slug')}")
        related = set(topic.get("related_cards", []))
        selected_cards = [card for card in cards if card.get("id") in related]
        raw_source_urls = topic.get("sources", [])
        if not isinstance(raw_source_urls, list) or not all(isinstance(url, str) for url in raw_source_urls):
            raise ValueError(f"evergreen topic {topic.get('slug')} sources must be a list of URLs")
        source_urls = list(dict.fromkeys(validate_citable_source_url(url) for url in raw_source_urls))
        source_articles = fetch_source_articles(source_urls)
        source_urls = [article["url"] for article in source_articles]
        brief = {**brief, "source_urls": source_urls}
        write_json(STATE / "todays-brief.json", brief)
        slots["BRIEF_JSON"] = json.dumps(brief, ensure_ascii=False, indent=2)
        required_source_urls = set(source_urls)
        expected_slug = str(topic["slug"])
        prompt_topic = {**topic, "sources": source_urls}
        slots.update({
            "TOPIC_JSON": json.dumps(prompt_topic, ensure_ascii=False, indent=2),
            "SOURCE_ARTICLES": json.dumps(source_articles, ensure_ascii=False, indent=2),
            "CARDS_JSON": json.dumps([compact_card(card) for card in selected_cards], ensure_ascii=False, indent=2),
        })
        template_name = "draft-evergreen.md"
    else:
        urls = brief.get("source_urls")
        if not isinstance(urls, list) or not urls:
            raise ValueError("news brief requires source_urls")
        urls = list(dict.fromkeys(validate_citable_source_url(str(url)) for url in urls))
        articles = fetch_source_articles(urls)
        urls = [article["url"] for article in articles]
        brief = {**brief, "source_urls": urls}
        write_json(STATE / "todays-brief.json", brief)
        slots["BRIEF_JSON"] = json.dumps(
            brief,
            ensure_ascii=False,
            indent=2,
        )
        haystack = json.dumps(brief, ensure_ascii=False) + " " + " ".join(item["text"] for item in articles)
        selected_cards = news_cards(cards, haystack)
        slots.update({
            "SOURCE_ARTICLES": json.dumps(articles, ensure_ascii=False, indent=2),
            "CARDS_JSON": json.dumps([compact_card(card) for card in selected_cards], ensure_ascii=False, indent=2),
        })
        template_name = "draft-news.md"

    template = (TOOLS / "prompts" / template_name).read_text(encoding="utf-8")
    prompt = fill_template(template, slots)
    allowed_ids = {int(card["id"]) for card in selected_cards}
    allowed_source_urls = {
        canonical_card_source_url(card)
        for card in selected_cards
        if card.get("card_url")
    }
    if brief["type"] == "news":
        allowed_source_urls.update(str(url) for url in urls)
    else:
        allowed_source_urls.update(required_source_urls)
    if revise:
        expected_slug = str(previous_draft["slug"])
        forbidden_slugs.discard(expected_slug)
        prompt = (
            prompt
            + "\n\nYour previous draft failed independent verification with these problems:\n"
            + "\n".join(f"- {failure}" for failure in verification_failures)
            + "\nPrevious draft JSON:\n"
            + json.dumps(previous_draft, ensure_ascii=False, indent=2)
            + "\nRevise the draft to fix every listed problem while preserving the slug, topic, "
            "structure, and everything that was not flagged. Typical fixes: state any hypothetical "
            "assumption in the same sentence as the number it produces; remove or properly source "
            "unsupported numbers; keep every calculation consistent with the prose and the supplied "
            "unit rules. Return a corrected STRICT JSON object only."
        )
    reply = run_codex(prompt, reasoning_effort="high" if revise else "medium")
    try:
        result = validate_draft(
            parse_json_reply(reply), allowed_ids, allowed_source_urls, expected_slug,
            forbidden_slugs, required_source_urls, cards,
        )
    except Exception as first_error:
        correction = (
            prompt
            + "\n\nYour previous response failed validation: " + str(first_error)
            + "\nPrevious response:\n" + reply
            + "\nReturn a corrected STRICT JSON object only."
        )
        retry = run_codex(correction, reasoning_effort="high")
        result = validate_draft(
            parse_json_reply(retry), allowed_ids, allowed_source_urls, expected_slug,
            forbidden_slugs, required_source_urls, cards,
        )
    write_json(STATE / "draft.json", result)
    print(json.dumps({"title": result["title"], "slug": result["slug"]}, ensure_ascii=False))
    return result


def main() -> int:
    draft()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
