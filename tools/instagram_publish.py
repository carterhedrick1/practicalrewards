#!/usr/bin/env python3
"""Publish a generated Practical Rewards post to Instagram via the Graph API.

Usage:
  instagram_publish.py --check            validate the token and print the account
  instagram_publish.py --latest [--wait N] publish the newest entry in published.json
  instagram_publish.py --slug SLUG        publish social/<slug>/
  instagram_publish.py ... --dry-run      do everything except create/publish

Config lives outside the repo at ~/.config/practicalrewards/instagram.json:
  {"ig_user_id": "1784...", "access_token": "EAAB...", "api_version": "v21.0"}

Images must be publicly reachable on practicalrewards.com (Render deploys on
push), so the publisher waits for each image URL to return 200 before it asks
Instagram to fetch it. Publish records go to tools/state/instagram.json, which
is git-ignored so a publish never dirties the tree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from common import ROOT, STATE, read_json, write_json

CONFIG_PATH = Path("~/.config/practicalrewards/instagram.json").expanduser()
RECORDS_PATH = STATE / "instagram.json"
GRAPH = "https://graph.facebook.com"


class PublishError(RuntimeError):
    pass


def load_config() -> dict[str, str]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PublishError(f"missing config {CONFIG_PATH}") from error
    for key in ("ig_user_id", "access_token"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise PublishError(f"config is missing {key}")
    config.setdefault("api_version", "v21.0")
    return config


def graph(config: dict[str, str], method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    params["access_token"] = config["access_token"]
    url = f"{GRAPH}/{config['api_version']}/{path.lstrip('/')}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {})
            message = detail.get("error_user_msg") or detail.get("message") or body
        except Exception:
            message = body
        raise PublishError(f"{method} {path} failed ({error.code}): {message[:500]}") from error
    if not isinstance(payload, dict):
        raise PublishError(f"{method} {path} returned a non-object reply")
    return payload


def check_account(config: dict[str, str]) -> dict[str, Any]:
    return graph(config, "GET", config["ig_user_id"], {"fields": "id,username,name,media_count"})


def wait_for_urls(urls: list[str], timeout: int) -> None:
    deadline = time.time() + timeout
    pending = list(urls)
    while pending:
        remaining: list[str] = []
        for url in pending:
            try:
                request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "PracticalRewardsPublisher/1.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    if response.status == 200 and response.headers.get("Content-Type", "").startswith("image/"):
                        continue
            except Exception:
                pass
            remaining.append(url)
        pending = remaining
        if not pending:
            return
        if time.time() > deadline:
            raise PublishError("images are not live yet: " + ", ".join(pending))
        print(f"waiting for {len(pending)} image(s) to deploy...", flush=True)
        time.sleep(20)


def wait_for_container(config: dict[str, str], container_id: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while True:
        status = graph(config, "GET", container_id, {"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in {"ERROR", "EXPIRED"}:
            raise PublishError(f"container {container_id} ended in {code}: {status.get('status')}")
        if time.time() > deadline:
            raise PublishError(f"container {container_id} still {code} after {timeout}s")
        time.sleep(5)


def publish(record: dict[str, Any], config: dict[str, str], dry_run: bool, wait: int) -> dict[str, Any]:
    images = record["images"]
    caption = record["caption"]
    urls = [image["url"] for image in images]
    wait_for_urls(urls, wait)
    if dry_run:
        return {"state": "dry-run", "images": urls, "caption_length": len(caption)}
    user = config["ig_user_id"]
    if len(images) == 1:
        container = graph(config, "POST", f"{user}/media", {"image_url": urls[0], "caption": caption})
        creation_id = container["id"]
    else:
        children: list[str] = []
        for url in urls:
            child = graph(config, "POST", f"{user}/media", {"image_url": url, "is_carousel_item": "true"})
            children.append(child["id"])
        for child_id in children:
            wait_for_container(config, child_id)
        container = graph(config, "POST", f"{user}/media", {
            "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption,
        })
        creation_id = container["id"]
    wait_for_container(config, creation_id)
    published = graph(config, "POST", f"{user}/media_publish", {"creation_id": creation_id})
    media_id = published["id"]
    details = graph(config, "GET", media_id, {"fields": "id,permalink,shortcode,timestamp,media_type"})
    return {
        "state": "published",
        "media_id": media_id,
        "permalink": details.get("permalink"),
        "shortcode": details.get("shortcode"),
        "published_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "images": urls,
    }


def load_records() -> dict[str, Any]:
    records = read_json(RECORDS_PATH, {})
    return records if isinstance(records, dict) else {}


def latest_slug() -> str:
    published = read_json(STATE / "published.json", [])
    if not isinstance(published, list) or not published:
        raise PublishError("published.json is empty")
    return str(published[-1]["slug"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a Practical Rewards post to Instagram.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="validate the token and print the account")
    group.add_argument("--latest", action="store_true", help="publish the newest post in published.json")
    group.add_argument("--slug", help="publish social/<slug>/")
    parser.add_argument("--dry-run", action="store_true", help="validate images and config without posting")
    parser.add_argument("--wait", type=int, default=600, help="seconds to wait for images to deploy (default 600)")
    args = parser.parse_args()

    try:
        config = load_config()
        if args.check:
            account = check_account(config)
            print(json.dumps(account, indent=2))
            return 0
        slug = args.slug or latest_slug()
        record_path = ROOT / "social" / slug / "post.json"
        record = read_json(record_path)
        if not isinstance(record, dict) or not record.get("images"):
            raise PublishError(f"no generated Instagram post at {record_path}")
        records = load_records()
        existing = records.get(slug)
        if isinstance(existing, dict) and existing.get("state") == "published":
            print(f"already published: {existing.get('permalink')}")
            return 0
        result = publish(record, config, args.dry_run, args.wait)
        if result["state"] == "published":
            records[slug] = result
            write_json(RECORDS_PATH, records)
        print(json.dumps({"slug": slug, **result}, indent=2))
        return 0
    except PublishError as error:
        print(f"FAILURE: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
