#!/usr/bin/env python3
"""Build the local Instagram preview page (never deployed).

Writes preview/instagram/index.html, which the Mac mini's dev server serves at
http://carters-mac-mini.tailb1c452.ts.net:8000/preview/instagram/ . The
preview/ directory is git-ignored, so Render never publishes it. The page shows
every generated post as a phone-style carousel with its caption, the
profile-grid crop, and its publish state (ready, or live with the permalink).
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any

from common import ROOT, STATE, read_json

PREVIEW_DIR = ROOT / "preview" / "instagram"
PREVIEW_PATH = PREVIEW_DIR / "index.html"
PREVIEW_URL = "http://carters-mac-mini.tailb1c452.ts.net:8000/preview/instagram/"


def load_posts() -> list[dict[str, Any]]:
    records = read_json(STATE / "instagram.json", {})
    records = records if isinstance(records, dict) else {}
    published = read_json(STATE / "published.json", [])
    dates = {str(item.get("slug")): str(item.get("date", "")) for item in published if isinstance(item, dict)}
    posts: list[dict[str, Any]] = []
    for post_json in (ROOT / "social").glob("*/post.json"):
        record = read_json(post_json, {})
        if not isinstance(record, dict) or not record.get("images"):
            continue
        slug = str(record.get("slug", post_json.parent.name))
        record["publish"] = records.get(slug) if isinstance(records.get(slug), dict) else None
        record["post_date"] = dates.get(slug, "")
        posts.append(record)
    posts.sort(key=lambda item: (item.get("post_date", ""), item.get("created_at", "")), reverse=True)
    return posts


def render_post(post: dict[str, Any]) -> str:
    slug = html.escape(str(post["slug"]))
    title = html.escape(str(post.get("title", slug)))
    images = post["images"]
    slides = "".join(
        f'<img src="../../social/{slug}/{html.escape(image["file"])}" alt="slide {index}" loading="lazy">'
        for index, image in enumerate(images, start=1)
    )
    dots = "".join('<span></span>' for _ in images)
    caption = html.escape(str(post.get("caption", "")))
    publish = post.get("publish")
    if publish and publish.get("state") == "published":
        link = html.escape(str(publish.get("permalink", "")))
        state = f'<a class="state live" href="{link}" target="_blank" rel="noopener">LIVE · {html.escape(str(publish.get("published_at", ""))[:16])}</a>'
    else:
        state = '<span class="state ready">READY · posts when you say publish</span>'
    thumb = html.escape(images[0]["file"]).replace(".jpg", "-profile-thumb.png")
    fmt = html.escape(str(post.get("format", "")))
    cover_style = html.escape(str(post.get("cover_style", "")))
    date = html.escape(str(post.get("post_date", "")))
    return f'''
<section class="post" id="{slug}">
  <div class="phone">
    <header class="ig-head">
      <img class="avatar" src="../../favicons/android-chrome-192x192.png" alt="">
      <div><b>practical.rewards</b><small>{date}</small></div>
    </header>
    <div class="carousel" data-count="{len(images)}">{slides}</div>
    <div class="dots">{dots}</div>
    <div class="ig-actions">♡ &nbsp; ○ &nbsp; ➤</div>
    <div class="ig-caption"><b>practical.rewards</b> {caption}</div>
  </div>
  <aside class="meta">
    <h2><a href="../../blog/{slug}.html">{title}</a></h2>
    <p>{state}</p>
    <dl>
      <dt>Format</dt><dd>{fmt}, {len(images)} image{"s" if len(images) != 1 else ""}, {cover_style} cover</dd>
      <dt>Copy source</dt><dd>{html.escape(str(post.get("copy_source", "")))}</dd>
      <dt>Caption</dt><dd>{len(str(post.get("caption", "")))} characters</dd>
    </dl>
    <h3>Profile grid crop</h3>
    <img class="thumb" src="../../social/{slug}/{thumb}" alt="profile grid thumbnail">
    <h3>Link preview image</h3>
    <img class="og" src="../../social/{slug}/og.png" alt="open graph image">
    <p class="regen">Regenerate: <code>python3 tools/social.py {slug} --force</code></p>
  </aside>
</section>'''


def build_preview() -> Path:
    posts = load_posts()
    grid = "".join(
        f'<a href="#{html.escape(str(post["slug"]))}"><img src="../../social/{html.escape(str(post["slug"]))}/'
        f'{html.escape(post["images"][0]["file"]).replace(".jpg", "-profile-thumb.png")}" alt=""></a>'
        for post in posts
    )
    body = "".join(render_post(post) for post in posts) or "<p>No generated posts yet.</p>"
    stamp = dt.datetime.now().astimezone().strftime("%B %d, %Y %H:%M")
    page = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Instagram queue · Practical Rewards</title>
<style>
:root {{ color-scheme: light dark; --ink:#1c1917; --paper:#f5f5f4; --line:#d6d3d1; --green:#059669; --muted:#78716c; }}
body {{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--paper); color:var(--ink); }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#f5f5f4; --paper:#1c1917; --line:#44403c; --muted:#a8a29e; }} }}
.top {{ padding:20px clamp(16px,4vw,40px); border-bottom:1px solid var(--line); display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
.top h1 {{ font-size:20px; margin:0; }} .top small {{ color:var(--muted); }}
.grid {{ display:flex; gap:4px; padding:12px clamp(16px,4vw,40px); overflow-x:auto; }}
.grid img {{ width:96px; height:96px; object-fit:cover; display:block; border-radius:4px; }}
.post {{ display:grid; grid-template-columns: 400px 1fr; gap:32px; padding:32px clamp(16px,4vw,40px); border-bottom:1px solid var(--line); align-items:start; }}
@media (max-width: 820px) {{ .post {{ grid-template-columns:1fr; }} }}
.phone {{ width:400px; max-width:100%; background:#000; color:#fff; border-radius:28px; overflow:hidden; box-shadow:0 20px 50px rgba(0,0,0,.35); }}
.ig-head {{ display:flex; gap:10px; align-items:center; padding:12px 14px; font-size:14px; }}
.ig-head small {{ display:block; color:#a8a29e; font-size:12px; }}
.avatar {{ width:32px; height:32px; border-radius:50%; }}
.carousel {{ display:flex; overflow-x:auto; scroll-snap-type:x mandatory; scrollbar-width:none; aspect-ratio:4/5; }}
.carousel::-webkit-scrollbar {{ display:none; }}
.carousel img {{ width:100%; flex:0 0 100%; scroll-snap-align:start; object-fit:cover; display:block; }}
.dots {{ display:flex; gap:4px; justify-content:center; padding:8px; }}
.dots span {{ width:6px; height:6px; border-radius:50%; background:#57534e; }} .dots span:first-child {{ background:#3b82f6; }}
.ig-actions {{ padding:0 14px 6px; font-size:20px; letter-spacing:2px; }}
.ig-caption {{ padding:0 14px 18px; font-size:13.5px; white-space:pre-wrap; color:#e7e5e4; }}
.meta h2 {{ margin:0 0 8px; font-size:18px; }} .meta h2 a {{ color:inherit; }}
.meta h3 {{ font-size:13px; text-transform:uppercase; letter-spacing:1px; color:var(--muted); margin:22px 0 8px; }}
.state {{ display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; letter-spacing:.5px; }}
.state.ready {{ background:#fde68a; color:#78350f; }} .state.live {{ background:#dcfce7; color:#14532d; text-decoration:none; }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:4px 16px; margin:12px 0; }} dt {{ color:var(--muted); }} dd {{ margin:0; }}
.thumb {{ width:180px; height:180px; border-radius:4px; }} .og {{ width:100%; max-width:480px; border-radius:8px; border:1px solid var(--line); }}
.regen {{ color:var(--muted); font-size:13px; }} code {{ font-size:12px; }}
</style></head><body>
<div class="top"><h1>Instagram queue</h1><small>local preview only · rebuilt {stamp} · swipe or scroll each phone sideways</small></div>
<div class="grid">{grid}</div>
{body}
</body></html>'''
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(page, encoding="utf-8")
    return PREVIEW_PATH


def main() -> int:
    path = build_preview()
    print(f"{path} -> {PREVIEW_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
