#!/usr/bin/env python3
"""Generate Instagram slides, a caption, and an Open Graph image for one post.

Usage:
  social.py                 use the slug in tools/state/draft.json
  social.py <slug>          work from blog/<slug>.html (any published post)
  social.py --no-llm        deterministic copy only (no Codex call)
  social.py --out DIR       write somewhere other than social/<slug>/

The built article HTML is the only source of truth. The model writes copy;
every number and card name it produces is checked against the article before
anything is rendered, and slides that cannot fit are rejected, never clipped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from common import (
    ROOT, STATE, TOOLS, card_mentions, fill_template, html_to_text,
    parse_json_reply, read_json, run_codex, write_json,
)
from verify_post import numeric_tokens

sys.path.insert(0, str(TOOLS / "social"))
from render import (  # noqa: E402
    Cover, MathSlide, SlideOverflow, TextSlide, VerdictSlide, export,
)

SITE = "https://practicalrewards.com"
SOCIAL_DIR = ROOT / "social"
BASE_HASHTAGS = ["#CreditCards", "#CreditCardRewards", "#TravelRewards", "#PointsAndMiles", "#PersonalFinance"]
HASHTAG_RE = re.compile(r"^#[A-Za-z][A-Za-z0-9]{1,29}$")
FIRST_PERSON_RE = re.compile(r"(?<![A-Za-z])(I|I'm|I’m|I've|I’ve|my|me|mine)(?![A-Za-z])")
PLAIN_TEXT_MARKUP_RE = re.compile(r"<[^>]*>|&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]+);|https?://|#\w", re.IGNORECASE)


class CopyRejected(ValueError):
    """The model's copy failed a hard gate."""


# ---------------------------------------------------------------------------
# Article extraction
# ---------------------------------------------------------------------------


def _first(pattern: str, page: str, flags: int = re.S) -> str:
    match = re.search(pattern, page, flags)
    if not match:
        raise ValueError(f"could not find {pattern!r} in the built post")
    return match.group(1)


def load_post(slug: str) -> dict[str, Any]:
    page_path = ROOT / "blog" / f"{slug}.html"
    if not page_path.is_file():
        raise FileNotFoundError(f"blog/{slug}.html does not exist; build the post first")
    page = page_path.read_text(encoding="utf-8")
    title = html.unescape(_first(r"<h1>(.*?)</h1>", page)).strip()
    meta = html.unescape(_first(r'<meta name="description" content="([^"]*)"', page))
    date = _first(r'<time datetime="([^"]+)"', page)
    content_html = _first(r'<div class="article-content">(.*?)</div>\s*</article>', page)
    aria = html.unescape(_first(r'<svg class="pr-hero-content"[^>]*aria-label="([^"]*)"', page))

    draft = read_json(STATE / "draft.json", {})
    hero: dict[str, str]
    if isinstance(draft, dict) and draft.get("slug") == slug and isinstance(draft.get("hero"), dict):
        hero = {key: str(draft["hero"][key]).strip() for key in ("kicker", "stat", "label")}
    else:
        kicker, rest = aria.split(": ", 1)
        stat, label = rest.split(". ", 1)
        hero = {"kicker": kicker.strip(), "stat": stat.strip(), "label": label.strip()}

    card_art: Path | None = None
    art_match = re.search(r'pr-hero-art-card.*?<image href="([^"]+)"', page, re.S)
    if art_match:
        candidate = ROOT / html.unescape(art_match.group(1)).lstrip("/")
        if candidate.is_file():
            card_art = candidate

    math = extract_math(content_html)
    verdict_match = re.search(r'<section class="pr-verdict">(.*?)</section>', content_html, re.S)
    verdict_text = html_to_text(re.sub(r"<h3>.*?</h3>", " ", verdict_match.group(1), flags=re.S)) if verdict_match else ""

    article_text = html_to_text(content_html)
    return {
        "slug": slug,
        "title": title,
        "meta_description": meta,
        "date": date,
        "url": f"{SITE}/blog/{slug}.html",
        "hero": hero,
        "card_art": card_art,
        "math": math,
        "verdict_text": verdict_text,
        "article_text": article_text,
        "content_html": content_html,
    }


def extract_math(content_html: str) -> dict[str, Any] | None:
    """Return the first pr-math panel with 2-6 rows as slide data."""
    for section in re.finditer(r'<section class="pr-math">(.*?)</section>', content_html, re.S):
        body = section.group(1)
        title_match = re.search(r"<h3>(.*?)</h3>", body, re.S)
        title = html_to_text(title_match.group(1)) if title_match else "The math"
        rows: list[tuple[str, str]] = []
        total: tuple[str, str] | None = None
        for row in re.finditer(
            r'<div class="pr-math-row( pr-math-total)?">\s*<span class="pr-math-label">(.*?)</span>\s*'
            r'<span class="pr-math-amount">(.*?)</span>\s*</div>',
            body,
            re.S,
        ):
            label, amount = html_to_text(row.group(2)), html_to_text(row.group(3))
            if row.group(1):
                total = (label, amount)
            else:
                rows.append((label, amount))
        if 1 <= len(rows) <= 6 and (total or len(rows) >= 2):
            return {"title": title, "rows": rows, "total": total}
    return None


# ---------------------------------------------------------------------------
# Copy generation and gates
# ---------------------------------------------------------------------------


def article_number_tokens(post: dict[str, Any]) -> set[str]:
    haystack = " ".join([
        post["title"], post["meta_description"], post["article_text"],
        post["hero"]["kicker"], post["hero"]["stat"], post["hero"]["label"],
    ])
    return numeric_tokens(haystack, key_numbers=True, include_bare_years=True)


def article_card_ids(post: dict[str, Any], cards: list[dict[str, Any]]) -> set[Any]:
    haystack = " ".join([post["title"], post["article_text"], post["hero"]["label"]])
    return {mention[2].get("id") for mention in card_mentions(haystack, cards)}


def _same_value_elsewhere(token: str, allowed: set[str]) -> bool:
    """Accept "12 credits" when the article says "12 months": same value, different unit word."""
    match = re.fullmatch(r"(\$?)(\d+(?:\.\d+)?)([a-z%]*)", token)
    if not match:
        return False
    prefix, number, unit = match.groups()
    if prefix or unit in {"", "%", "x", "cpp", "point"}:
        return False  # money, percentages, multipliers, cpp, and points stay strict
    return any(re.fullmatch(rf"\$?{re.escape(number)}[a-z%]*", candidate) for candidate in allowed)


def check_text(field: str, value: Any, limit: int, allowed_numbers: set[str], allowed_cards: set[Any], cards: list[dict[str, Any]], minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise CopyRejected(f"{field} must be a string")
    value = re.sub(r"[ \t]+", " ", value.strip())
    if len(value) < minimum:
        raise CopyRejected(f"{field} is too short")
    if len(value) > limit:
        raise CopyRejected(f"{field} is {len(value)} characters; limit is {limit}")
    if PLAIN_TEXT_MARKUP_RE.search(value):
        raise CopyRejected(f"{field} must be plain text without markup, links, or hashtags")
    if "!" in value:
        raise CopyRejected(f"{field} contains an exclamation point")
    if FIRST_PERSON_RE.search(value):
        raise CopyRejected(f"{field} uses first-person singular")
    if re.search(r"\brumou?r\b", value, re.IGNORECASE):
        raise CopyRejected(f"{field} uses the word rumor")
    unsupported = {
        token for token in numeric_tokens(value, key_numbers=True, include_bare_years=True) - allowed_numbers
        if not _same_value_elsewhere(token, allowed_numbers)
    }
    if unsupported:
        raise CopyRejected(f"{field} contains numbers not in the article: {', '.join(sorted(unsupported))}")
    foreign = {mention[2].get("id") for mention in card_mentions(value, cards)} - allowed_cards
    if foreign:
        names = ", ".join(str(next(card["name"] for card in cards if card.get("id") == card_id)) for card_id in foreign)
        raise CopyRejected(f"{field} names cards the article does not: {names}")
    return value


def validate_copy(raw: Any, post: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CopyRejected("reply must be a JSON object")
    allowed_keys = {"format", "slides", "verdict", "caption", "extra_hashtags"}
    unexpected = sorted(raw.keys() - allowed_keys)
    if unexpected:
        raise CopyRejected("unexpected keys: " + ", ".join(unexpected))
    missing = sorted({"format", "slides", "verdict", "caption"} - raw.keys())
    if missing:
        raise CopyRejected("missing keys: " + ", ".join(missing))
    fmt = raw["format"]
    if fmt not in {"single", "carousel"}:
        raise CopyRejected("format must be single or carousel")
    allowed_numbers = article_number_tokens(post)
    allowed_cards = article_card_ids(post, cards)
    slides_raw = raw["slides"]
    if not isinstance(slides_raw, list):
        raise CopyRejected("slides must be a list")
    if fmt == "single" and slides_raw:
        raise CopyRejected("single format must have no text slides")
    if fmt == "carousel" and not 1 <= len(slides_raw) <= 2:
        raise CopyRejected("carousel format needs 1 or 2 text slides")
    slides: list[dict[str, str]] = []
    for index, slide in enumerate(slides_raw, start=1):
        if not isinstance(slide, dict) or set(slide) != {"heading", "body"}:
            raise CopyRejected(f"slide {index} must have exactly heading and body")
        slides.append({
            "heading": check_text(f"slide {index} heading", slide["heading"], 40, allowed_numbers, allowed_cards, cards, minimum=6),
            "body": check_text(f"slide {index} body", slide["body"], 170, allowed_numbers, allowed_cards, cards, minimum=20),
        })
    verdict = check_text("verdict", raw["verdict"], 190, allowed_numbers, allowed_cards, cards, minimum=30)
    caption = check_text("caption", raw["caption"], 1000, allowed_numbers, allowed_cards, cards, minimum=350)
    extra = raw.get("extra_hashtags", [])
    if not isinstance(extra, list) or len(extra) > 3 or not all(isinstance(tag, str) and HASHTAG_RE.match(tag) for tag in extra):
        raise CopyRejected("extra_hashtags must be 0-3 #CamelCase tags")
    if post["math"] is None and fmt == "carousel" and not slides:
        raise CopyRejected("carousel without math needs at least one text slide")
    return {"format": fmt, "slides": slides, "verdict": verdict, "caption": caption, "extra_hashtags": [tag for tag in extra if tag not in BASE_HASHTAGS]}


def fallback_copy(post: dict[str, Any]) -> dict[str, Any]:
    """Deterministic copy used when the model is unavailable or rejected twice."""
    verdict = post["verdict_text"] or post["meta_description"]
    sentences = re.split(r"(?<=[.?])\s+", verdict)
    short = ""
    for sentence in sentences:
        if len(short) + len(sentence) + 1 > 190:
            break
        short = f"{short} {sentence}".strip()
    if not short:
        short = post["meta_description"][:187].rstrip() + "…"
    caption = f"{post['title']}\n\n{post['meta_description']}"
    if post["verdict_text"]:
        caption += f"\n\nThe practical verdict: {post['verdict_text']}"
    return {
        "format": "carousel" if post["math"] else "single",
        "slides": [],
        "verdict": short,
        "caption": caption[:800],
        "extra_hashtags": [],
    }


def request_copy(post: dict[str, Any], cards: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    template = (TOOLS / "prompts" / "social.md").read_text(encoding="utf-8")
    style = (TOOLS / "content" / "style-guide.md").read_text(encoding="utf-8")
    math_json = "null"
    if post["math"]:
        math_json = json.dumps({"title": post["math"]["title"], "rows": post["math"]["rows"], "total": post["math"]["total"]}, ensure_ascii=False)
    prompt = fill_template(template, {
        "STYLE_GUIDE": style,
        "TITLE": post["title"],
        "URL": post["url"],
        "META_DESCRIPTION": post["meta_description"],
        "HERO_JSON": json.dumps(post["hero"], ensure_ascii=False),
        "MATH_JSON": math_json,
        "VERDICT_TEXT": post["verdict_text"] or "(none)",
        "ARTICLE_TEXT": post["article_text"],
    })
    reply = run_codex(prompt, reasoning_effort="medium")
    try:
        return validate_copy(parse_json_reply(reply), post, cards), "codex"
    except (CopyRejected, ValueError) as first_error:
        print(f"Note: first social copy rejected ({first_error}); requesting a correction", file=sys.stderr)
        correction = (
            prompt
            + "\n\nYour previous response failed validation: " + str(first_error)
            + "\nPrevious response:\n" + reply
            + "\nReturn a corrected STRICT JSON object only."
        )
        retry = run_codex(correction, reasoning_effort="medium")
        return validate_copy(parse_json_reply(retry), post, cards), "codex-retry"


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def cover_style(slug: str, card_art: Path | None) -> str:
    """Rotate cover styles so the grid alternates instead of repeating.

    Posts with card art always use the dark slate cover (the card reads best on
    it). Everything else alternates dark/light by position in published.json,
    so consecutive art-free posts never share a look.
    """
    if card_art is not None:
        return "dark"
    published = read_json(STATE / "published.json", [])
    slugs = [str(item.get("slug", "")) for item in published if isinstance(item, dict)]
    position = slugs.index(slug) if slug in slugs else len(slugs)
    return "light" if position % 2 else "dark"


def build_slides(post: dict[str, Any], copy: dict[str, Any]) -> list[Any]:
    cover = Cover(
        post["hero"]["kicker"], post["hero"]["stat"], post["hero"]["label"], post["card_art"],
        style=cover_style(post["slug"], post["card_art"]),
    )
    if copy["format"] == "single":
        return [cover]
    slides: list[Any] = [cover]
    if post["math"]:
        slides.append(MathSlide(post["math"]["title"], post["math"]["rows"], post["math"]["total"]))
    for slide in copy["slides"]:
        slides.append(TextSlide(slide["heading"], slide["body"]))
    slides.append(VerdictSlide(copy["verdict"]))
    return slides


def compose_caption(post: dict[str, Any], copy: dict[str, Any]) -> str:
    tags = " ".join(BASE_HASHTAGS + copy["extra_hashtags"])
    caption = (
        f"{copy['caption']}\n\n"
        f"Full breakdown on practicalrewards.com (link in bio).\n\n"
        f"{tags}"
    )
    if len(caption) > 2200:
        raise CopyRejected("caption exceeds Instagram's 2,200 character limit")
    return caption


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(slug: str, out_dir: Path, use_llm: bool, force: bool) -> dict[str, Any]:
    post = load_post(slug)
    cards = read_json(ROOT / "cards.json", [])
    if out_dir.exists():
        if not force and any(out_dir.iterdir()):
            raise FileExistsError(f"{out_dir} already exists; pass --force to regenerate")
        shutil.rmtree(out_dir)

    copy_source = "fallback"
    copy: dict[str, Any] | None = None
    if use_llm:
        try:
            copy, copy_source = request_copy(post, cards)
        except Exception as error:
            print(f"WARNING: social copy from Codex rejected or unavailable ({error}); using deterministic copy", file=sys.stderr)
    if copy is None:
        copy = fallback_copy(post)

    # Render, dropping text slides one at a time if the template cannot fit them.
    slides = build_slides(post, copy)
    while True:
        try:
            exported = export(slides, out_dir, cover_for_og=slides[0])
            break
        except SlideOverflow as error:
            text_indexes = [index for index, slide in enumerate(slides) if isinstance(slide, TextSlide)]
            if text_indexes:
                dropped = slides.pop(text_indexes[-1])
                print(f"WARNING: dropped a text slide that did not fit ({error}): {dropped.heading!r}", file=sys.stderr)
                continue
            if any(isinstance(slide, VerdictSlide) for slide in slides) and copy_source != "fallback-verdict":
                copy["verdict"] = fallback_copy(post)["verdict"]
                slides = [slide if not isinstance(slide, VerdictSlide) else VerdictSlide(copy["verdict"]) for slide in slides]
                copy_source = "fallback-verdict"
                continue
            raise
    caption = compose_caption(post, copy)
    (out_dir / "caption.md").write_text(caption + "\n", encoding="utf-8")

    created = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    images = [
        {
            "file": path.name,
            "url": f"{SITE}/social/{slug}/{path.name}",
            "sha256": sha256(path),
        }
        for path in exported
    ]
    record = {
        "slug": slug,
        "title": post["title"],
        "url": post["url"],
        "format": "single" if len(exported) == 1 else "carousel",
        "created_at": created,
        "copy_source": copy_source,
        "images": images,
        "og_image": f"{SITE}/social/{slug}/og.png",
        "caption": caption,
        "cover_style": slides[0].style,
        "slides": [
            {"type": type(slide).__name__, **({"heading": slide.heading, "body": slide.body} if isinstance(slide, TextSlide) else {})}
            for slide in slides
        ],
    }
    write_json(out_dir / "post.json", record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Instagram assets for a Practical Rewards post.")
    parser.add_argument("slug", nargs="?", help="post slug (defaults to tools/state/draft.json)")
    parser.add_argument("--no-llm", action="store_true", help="skip Codex and use deterministic copy")
    parser.add_argument("--out", type=Path, help="output directory (default social/<slug>)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    slug = args.slug
    if not slug:
        draft = read_json(STATE / "draft.json", {})
        slug = str(draft.get("slug", "")) if isinstance(draft, dict) else ""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug or ""):
        print("ERROR: a valid post slug is required", file=sys.stderr)
        return 2
    out_dir = args.out or (SOCIAL_DIR / slug)
    record = generate(slug, out_dir, use_llm=not args.no_llm, force=args.force)
    print(json.dumps({
        "slug": slug, "format": record["format"], "images": len(record["images"]),
        "copy_source": record["copy_source"], "dir": str(out_dir),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
