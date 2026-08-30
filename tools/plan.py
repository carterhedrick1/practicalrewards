#!/usr/bin/env python3
"""Select today's timely-news or deterministic evergreen assignment."""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

from common import (
    STATE, TOOLS, fill_template, is_google_news_url, parse_json_reply,
    read_json, run_codex, validate_public_http_url, write_json,
)


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


def source_is_unresolved(item: dict[str, Any]) -> bool:
    return item.get("unresolved_source") is True or is_google_news_url(str(item.get("url", "")))


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
    allowed = {
        str(item.get("url"))
        for item in inbox
        if isinstance(item, dict) and not source_is_unresolved(item)
    }
    if any(not isinstance(url, str) or url not in allowed for url in urls):
        raise ValueError("news plan contains a URL not present in the selectable inbox or marked unresolved")
    safe_urls = [validate_public_http_url(url) for url in urls]
    return {"type": "news", "title_hint": title.strip(), "source_urls": list(dict.fromkeys(safe_urls))}


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
    selectable_inbox = [
        item for item in inbox
        if isinstance(item, dict) and not source_is_unresolved(item)
    ]
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
    deterministic = {"type": "evergreen", "slug": fallback["slug"]}
    try:
        reply = run_codex(prompt, reasoning_effort="low")
        brief = validate_model_plan(parse_json_reply(reply), fallback, selectable_inbox)
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
