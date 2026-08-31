#!/usr/bin/env python3
"""Select today's timely-news or deterministic evergreen assignment."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from typing import Any

from common import (
    STATE, TOOLS, fill_template, is_google_news_url, parse_json_reply,
    read_json, resolve_google_news_source_url, run_codex,
    validate_public_http_url, write_json,
)
from ingest import record_seen_aliases


def load_published() -> list[dict[str, Any]]:
    path = STATE / "published.json"
    if not path.exists():
        write_json(path, [])
        return []
    value = read_json(path, [])
    if not isinstance(value, list):
        raise ValueError("tools/state/published.json must contain a JSON list")
    return value


def next_evergreen(topics: list[dict[str, Any]], published: list[dict[str, Any]]) -> dict[str, Any]:
    published_slugs = {str(item.get("slug")) for item in published if isinstance(item, dict)}
    candidates = [
        (int(topic.get("priority", 999999)), index, topic)
        for index, topic in enumerate(topics)
        if str(topic.get("slug")) not in published_slugs
    ]
    if not candidates:
        raise RuntimeError("all evergreen topics have already been published")
    return min(candidates, key=lambda row: (row[0], row[1]))[2]


def validate_model_plan(value: Any, fallback: dict[str, Any], inbox: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("planner reply must be a JSON object")
    if value.get("type") == "evergreen":
        if value.get("slug") != fallback["slug"]:
            raise ValueError("planner selected an evergreen slug other than the supplied fallback")
        return {"type": "evergreen", "slug": fallback["slug"]}
    if value.get("type") != "news":
        raise ValueError("planner type must be news or evergreen")
    title = value.get("title_hint")
    urls = value.get("source_urls")
    if not isinstance(title, str) or not title.strip() or not isinstance(urls, list) or not urls:
        raise ValueError("news plan requires title_hint and at least one source URL")
    allowed = {str(item.get("url")) for item in inbox if isinstance(item, dict)}
    if any(not isinstance(url, str) or url not in allowed for url in urls):
        raise ValueError("news plan contains a URL not present in the inbox")
    safe_urls = [validate_public_http_url(url) for url in urls]
    return {"type": "news", "title_hint": title.strip(), "source_urls": list(dict.fromkeys(safe_urls))}


def resolve_selected_news_sources(brief: dict[str, Any]) -> dict[str, Any]:
    """Resolve and retain only safe publisher URLs for a selected news story."""
    resolved_urls: list[str] = []
    alias_pairs: list[tuple[str, str]] = []
    for source_url in brief["source_urls"]:
        try:
            resolved_url, unresolved = resolve_google_news_source_url(source_url)
            if unresolved or is_google_news_url(resolved_url):
                raise ValueError("Google News wrapper did not resolve to a publisher URL")
            resolved_urls.append(validate_public_http_url(resolved_url))
            if resolved_url != source_url:
                alias_pairs.append((source_url, resolved_url))
        except Exception as error:
            print(
                f"WARNING: selected news source could not be resolved safely "
                f"{source_url!r}: {error}",
                file=sys.stderr,
            )

    resolved_urls = list(dict.fromkeys(resolved_urls))
    if not resolved_urls:
        raise ValueError("none of the selected story's sources resolved to a safe public URL")
    record_seen_aliases(STATE / "seen.json", alias_pairs)
    return {**brief, "source_urls": resolved_urls}


def plan() -> dict[str, Any]:
    STATE.mkdir(parents=True, exist_ok=True)
    inbox = read_json(STATE / "inbox.json", [])
    if not isinstance(inbox, list):
        raise ValueError("tools/state/inbox.json must contain a JSON list")
    topic_map = read_json(TOOLS / "content" / "topic-map.json")
    topics = topic_map.get("topics", []) if isinstance(topic_map, dict) else []
    if not isinstance(topics, list):
        raise ValueError("topic-map.json has no topics list")
    published = load_published()
    fallback = next_evergreen(topics, published)
    deterministic = {"type": "evergreen", "slug": fallback["slug"]}
    if os.environ.get("PLAN_FORCE_EVERGREEN"):
        write_json(STATE / "todays-brief.json", deterministic)
        print(json.dumps(deterministic, ensure_ascii=False))
        return deterministic
    selectable_inbox = [item for item in inbox if isinstance(item, dict)]
    template = (TOOLS / "prompts" / "plan.md").read_text(encoding="utf-8")
    prompt = fill_template(template, {
        "TODAY": dt.date.today().isoformat(),
        "EVERGREEN_FALLBACK": json.dumps(
            {key: fallback.get(key) for key in ("slug", "title", "thesis", "priority")},
            ensure_ascii=False,
            indent=2,
        ),
        "INBOX_JSON": json.dumps(selectable_inbox, ensure_ascii=False, indent=2),
    })
    try:
        reply = run_codex(prompt, reasoning_effort="low")
        brief = validate_model_plan(parse_json_reply(reply), fallback, selectable_inbox)
        if brief["type"] == "news":
            brief = resolve_selected_news_sources(brief)
    except Exception as error:
        print(f"WARNING: planner output unusable; using evergreen fallback: {error}", file=sys.stderr)
        brief = deterministic
    write_json(STATE / "todays-brief.json", brief)
    print(json.dumps(brief, ensure_ascii=False))
    return brief


def main() -> int:
    plan()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
