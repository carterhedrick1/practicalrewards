#!/usr/bin/env python3
"""Deterministic Instagram and Open Graph image renderer for Practical Rewards.

Every slide is a fixed, measured layout in the site's slate-and-forest palette.
Text never overflows: each block is fitted with a shrink-to-fit search and the
renderer raises SlideOverflow when copy cannot fit inside its box at the minimum
size, so callers can shorten the copy instead of shipping a clipped slide.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]

W, H = 1080, 1350
SQUARE_TOP, SQUARE_BOTTOM = (H - W) // 2, (H - W) // 2 + W  # 135 .. 1215
MARGIN = 96

# Palette: mirrors css/styles.css and the post hero in tools/build_post.py.
SLATE = ("#0f2027", "#203a43", "#2c5364")
GREEN, GREEN_LIGHT, MINT = "#059669", "#22c55e", "#34d399"
INK, INK_SOFT, MUTED = "#1c1917", "#44403c", "#78716c"
PAPER, PAPER_LINE, WHITE = "#f5f5f4", "#d6d3d1", "#ffffff"
CLOUD = "#e7e5e4"
GOLD = "#fde68a"

SF = "/System/Library/Fonts/SFNS.ttf"
HELVETICA = "/System/Library/Fonts/HelveticaNeue.ttc"
MARK = ROOT / "favicons" / "android-chrome-512x512.png"


class SlideOverflow(ValueError):
    """Copy cannot fit inside its box even at the minimum font size."""


_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    try:
        face = ImageFont.truetype(SF, size)
        face.set_variation_by_name(weight)
    except Exception:
        index = {"Regular": 0, "Medium": 10, "Semibold": 1, "Bold": 1, "Heavy": 1, "Black": 1}.get(weight, 0)
        face = ImageFont.truetype(HELVETICA, size, index=index)
    _font_cache[key] = face
    return face


def text_width(draw: ImageDraw.ImageDraw, value: str, face: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), value, font=face)
    return right - left


def wrap(draw: ImageDraw.ImageDraw, value: str, face: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in value.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if text_width(draw, trial, face) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


@dataclass
class Fitted:
    face: ImageFont.FreeTypeFont
    lines: list[str]
    line_height: int
    size: int

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)


def fit(
    draw: ImageDraw.ImageDraw,
    value: str,
    weight: str,
    max_width: int,
    max_height: int,
    start: int,
    minimum: int,
    leading: float = 1.22,
    max_lines: int | None = None,
    step: int = 2,
) -> Fitted:
    for size in range(start, minimum - 1, -step):
        face = font(weight, size)
        lines = wrap(draw, value, face, max_width)
        line_height = round(size * leading)
        too_wide = any(text_width(draw, line, face) > max_width for line in lines)
        if too_wide:
            continue
        if line_height * len(lines) <= max_height and (max_lines is None or len(lines) <= max_lines):
            return Fitted(face, lines, line_height, size)
    raise SlideOverflow(f"text does not fit at {minimum}px: {value[:60]!r}")


def draw_lines(
    draw: ImageDraw.ImageDraw,
    fitted: Fitted,
    x: int,
    y: int,
    fill: str,
    align: str = "left",
    box_width: int | None = None,
) -> int:
    for line in fitted.lines:
        if align == "right" and box_width is not None:
            line_x = x + box_width - text_width(draw, line, fitted.face)
        elif align == "center" and box_width is not None:
            line_x = x + (box_width - text_width(draw, line, fitted.face)) // 2
        else:
            line_x = x
        draw.text((line_x, y), line, font=fitted.face, fill=fill)
        y += fitted.line_height
    return y


def tracked_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    value: str,
    face: ImageFont.FreeTypeFont,
    fill: str,
    tracking: int,
) -> int:
    x, y = position
    for character in value:
        draw.text((x, y), character, font=face, fill=fill)
        x += text_width(draw, character, face) + tracking
    return x


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def diagonal_gradient(width: int, height: int, stops: tuple[str, ...]) -> Image.Image:
    """Top-left to bottom-right gradient, matching the hero ground."""
    colors = [hex_rgb(stop) for stop in stops]
    ramp = Image.new("RGB", (width + height, 1))
    pixels = ramp.load()
    total = width + height - 1
    for index in range(width + height):
        position = index / total * (len(colors) - 1)
        low = int(math.floor(position))
        high = min(low + 1, len(colors) - 1)
        mix = position - low
        pixels[index, 0] = tuple(
            round(colors[low][channel] * (1 - mix) + colors[high][channel] * mix) for channel in range(3)
        )
    canvas = Image.new("RGB", (width, height))
    for y in range(height):
        row = ramp.crop((y, 0, y + width, 1))
        canvas.paste(row, (0, y))
    return canvas


def vertical_gradient(width: int, height: int, top: str, bottom: str) -> Image.Image:
    a, b = hex_rgb(top), hex_rgb(bottom)
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        mix = y / max(height - 1, 1)
        pixels[0, y] = tuple(round(a[channel] * (1 - mix) + b[channel] * mix) for channel in range(3))
    return strip.resize((width, height))


def card_texture(canvas: Image.Image, alpha: int = 5, color: tuple[int, int, int] = (255, 255, 255)) -> None:
    """Faint tiled card silhouettes, echoing the site header background."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fill = (*color, alpha)
    tile_w, tile_h = 180, 120
    for row in range(-1, canvas.height // tile_h + 2):
        for column in range(-1, canvas.width // tile_w + 2):
            x = column * tile_w + (tile_w // 2 if row % 2 else 0)
            y = row * tile_h
            draw.rounded_rectangle((x + 30, y + 22, x + 150, y + 97), radius=12, fill=fill)
            draw.rounded_rectangle((x + 38, y + 52, x + 75, y + 58), radius=3, fill=fill)
            draw.rounded_rectangle((x + 82, y + 52, x + 105, y + 58), radius=3, fill=fill)
            draw.rounded_rectangle((x + 38, y + 67, x + 105, y + 72), radius=2, fill=fill)
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"))


def accent_bar(canvas: Image.Image, x: int, top: int, bottom: int, width: int = 10) -> None:
    bar = vertical_gradient(width, bottom - top, GREEN, GREEN_LIGHT)
    mask = Image.new("L", bar.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, bottom - top - 1), radius=width // 2, fill=255)
    canvas.paste(bar, (x, top), mask)


def brand_row(canvas: Image.Image, draw: ImageDraw.ImageDraw, y: int, dark: bool, x: int = MARGIN) -> None:
    mark = Image.open(MARK).convert("RGBA").resize((56, 56), Image.Resampling.LANCZOS)
    canvas.paste(mark, (x, y), mark)
    face = font("Semibold", 34)
    draw.text((x + 72, y + 6), "Practical Rewards", font=face, fill=WHITE if dark else INK)


def footer(draw: ImageDraw.ImageDraw, index: int, total: int, dark: bool) -> None:
    y = 1262
    face = font("Medium", 28)
    draw.text((MARGIN, y), "practicalrewards.com", font=face, fill=CLOUD if dark else MUTED)
    if total > 1:
        counter = f"{index}/{total}"
        draw.text((W - MARGIN - text_width(draw, counter, face), y), counter, font=face, fill=MINT if dark else GREEN)


def swipe_cue(draw: ImageDraw.ImageDraw, dark: bool) -> None:
    face = font("Semibold", 26)
    label = "Swipe for the math"
    width = text_width(draw, label, face)
    x = MARGIN
    y = 1190
    draw.text((x, y), label, font=face, fill=MINT if dark else GREEN)
    arrow_x = x + width + 16
    color = MINT if dark else GREEN
    draw.line((arrow_x, y + 16, arrow_x + 24, y + 16), fill=color, width=4)
    draw.line((arrow_x + 14, y + 6, arrow_x + 24, y + 16), fill=color, width=4)
    draw.line((arrow_x + 14, y + 26, arrow_x + 24, y + 16), fill=color, width=4)


def load_card_art(path: Path | None, width: int) -> Image.Image | None:
    if path is None or not path.is_file():
        return None
    try:
        art = Image.open(path).convert("RGBA")
    except Exception:
        return None
    if art.width < 80 or art.height < 50:
        return None
    ratio = art.height / art.width
    if not 0.55 <= ratio <= 0.72:
        # Not a card-shaped asset; skip rather than distort it.
        return None
    art = art.resize((width, round(width * ratio)), Image.Resampling.LANCZOS)
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, art.width - 1, art.height - 1), radius=round(width * 0.055), fill=255)
    rounded = Image.new("RGBA", art.size, (0, 0, 0, 0))
    rounded.paste(art, (0, 0), mask)
    return rounded


def paste_card(canvas: Image.Image, art: Image.Image, center: tuple[int, int], angle: float = -8.0) -> None:
    rotated = art.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    shadow = Image.new("RGBA", (rotated.width + 120, rotated.height + 120), (0, 0, 0, 0))
    shadow_mask = rotated.getchannel("A")
    shadow.paste((0, 0, 0, 150), (60, 78), shadow_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    x = center[0] - rotated.width // 2
    y = center[1] - rotated.height // 2
    base = canvas.convert("RGBA")
    base.alpha_composite(shadow, (x - 60, y - 60))
    base.alpha_composite(rotated, (x, y))
    canvas.paste(base.convert("RGB"))


# --------------------------------------------------------------------------
# Slide models
# --------------------------------------------------------------------------


@dataclass
class Cover:
    kicker: str
    stat: str
    label: str
    card_art: Path | None = None
    style: str = "dark"  # "dark" (slate gradient) or "light" (paper)


@dataclass
class TextSlide:
    heading: str
    body: str


@dataclass
class MathSlide:
    title: str
    rows: list[tuple[str, str]]
    total: tuple[str, str] | None


@dataclass
class VerdictSlide:
    body: str
    cta: str = "Read the full math"


Slide = Union[Cover, TextSlide, MathSlide, VerdictSlide]


# --------------------------------------------------------------------------
# Slide renderers
# --------------------------------------------------------------------------


def _dark_canvas() -> Image.Image:
    canvas = diagonal_gradient(W, H, SLATE)
    card_texture(canvas)
    return canvas


def render_cover(slide: Cover, index: int, total: int) -> Image.Image:
    dark = slide.style != "light"
    if dark:
        canvas = _dark_canvas()
    else:
        canvas = _light_canvas()
        card_texture(canvas, alpha=6, color=(28, 25, 23))
    draw = ImageDraw.Draw(canvas)
    brand_row(canvas, draw, 176, dark=dark)
    kicker_color = MINT if dark else GREEN
    stat_color = WHITE if dark else INK
    label_color = CLOUD if dark else INK_SOFT

    text_x = MARGIN + 44
    text_w = W - text_x - MARGIN
    art = load_card_art(slide.card_art, 400)
    kicker_face = font("Bold", 30)
    stat = fit(draw, slide.stat, "Black", text_w, 260, 230, 96, leading=1.0, max_lines=1, step=6)
    label = fit(draw, slide.label, "Medium", text_w, 200, 48, 34, leading=1.24, max_lines=3)
    stat_box = draw.textbbox((0, 0), slide.stat, font=stat.face)
    block_h = 64 + (stat_box[3] - stat_box[1]) + 40 + label.height
    if art is not None:
        kicker_y = 430
    else:
        kicker_y = 330 + (1180 - 330 - block_h) // 2
    tracked_text(draw, (text_x, kicker_y), slide.kicker.upper(), kicker_face, kicker_color, 7)
    stat_y = kicker_y + 64
    draw.text((text_x - stat_box[0], stat_y - stat_box[1]), slide.stat, font=stat.face, fill=stat_color)
    stat_bottom = stat_y + (stat_box[3] - stat_box[1])
    label_bottom = draw_lines(draw, label, text_x, stat_bottom + 40, label_color)
    accent_bar(canvas, MARGIN, kicker_y - 6, label_bottom + 4)

    if art is not None:
        paste_card(canvas, art, (W - MARGIN - 170, 1030))
    if total > 1:
        swipe_cue(draw, dark=dark)
    footer(draw, index, total, dark=dark)
    return canvas

def _light_canvas() -> Image.Image:
    return Image.new("RGB", (W, H), PAPER)


def render_text(slide: TextSlide, index: int, total: int) -> Image.Image:
    canvas = _light_canvas()
    draw = ImageDraw.Draw(canvas)
    brand_row(canvas, draw, 176, dark=False)
    text_x = MARGIN + 44
    text_w = W - text_x - MARGIN
    number_face = font("Bold", 30)
    heading = fit(draw, slide.heading, "Bold", text_w, 240, 68, 44, leading=1.12, max_lines=3)
    body = fit(draw, slide.body, "Regular", text_w, 420, 44, 32, leading=1.36, max_lines=8)
    block_h = 62 + heading.height + 36 + body.height
    number_y = 320 + (1200 - 320 - block_h) // 2
    tracked_text(draw, (text_x, number_y), f"{index - 1:02d}", number_face, GREEN, 4)
    heading_y = number_y + 62
    heading_bottom = draw_lines(draw, heading, text_x, heading_y, INK)
    body_y = heading_bottom + 36
    body_bottom = draw_lines(draw, body, text_x, body_y, INK_SOFT)
    if body_bottom > SQUARE_BOTTOM - 40:
        raise SlideOverflow("text slide body runs past the square-safe area")
    accent_bar(canvas, MARGIN, number_y - 6, body_bottom + 2)
    footer(draw, index, total, dark=False)
    return canvas


def render_math(slide: MathSlide, index: int, total: int) -> Image.Image:
    canvas = _light_canvas()
    draw = ImageDraw.Draw(canvas)
    brand_row(canvas, draw, 176, dark=False)
    text_x = MARGIN + 44
    text_w = W - text_x - MARGIN
    number_face = font("Bold", 30)
    title = fit(draw, slide.title, "Bold", text_w, 160, 60, 40, leading=1.12, max_lines=2)
    rows = list(slide.rows)
    row_h = 92
    total_h = 118 if slide.total else 0
    panel_h = 36 + row_h * len(rows) + total_h + 36
    block_h = 62 + title.height + 40 + panel_h
    if block_h > 1200 - 320:
        raise SlideOverflow("math panel runs past the square-safe area")
    number_y = 320 + (1200 - 320 - block_h) // 2
    tracked_text(draw, (text_x, number_y), f"{index - 1:02d}", number_face, GREEN, 4)
    title_bottom = draw_lines(draw, title, text_x, number_y + 62, INK)

    # Panel
    panel_top = title_bottom + 40
    panel_bottom = panel_top + panel_h
    draw.rounded_rectangle((MARGIN, panel_top, W - MARGIN, panel_bottom), radius=26, fill=WHITE, outline=PAPER_LINE, width=2)
    inner_x = MARGIN + 44
    inner_w = W - 2 * MARGIN - 88
    y = panel_top + 36
    label_face, amount_face = font("Regular", 38), font("Semibold", 40)
    for label_text, amount in rows:
        label_fit = fit(draw, label_text, "Regular", inner_w - 260, row_h, 38, 26, leading=1.1, max_lines=2)
        draw_lines(draw, label_fit, inner_x, y + (row_h - label_fit.height) // 2 - 6, INK_SOFT)
        amount_w = text_width(draw, amount, amount_face)
        draw.text((inner_x + inner_w - amount_w, y + 18), amount, font=amount_face, fill=INK)
        y += row_h
        draw.line((inner_x, y, inner_x + inner_w, y), fill=PAPER_LINE, width=2)
    if slide.total:
        label_text, amount = slide.total
        draw.line((inner_x, y, inner_x + inner_w, y), fill=GREEN, width=4)
        total_label = fit(draw, label_text, "Bold", inner_w - 300, total_h, 40, 26, leading=1.1, max_lines=2)
        draw_lines(draw, total_label, inner_x, y + (total_h - total_label.height) // 2 - 4, INK)
        amount_fit = fit(draw, amount, "Bold", 300, total_h, 52, 26, leading=1.0, max_lines=2)
        draw_lines(draw, amount_fit, inner_x + inner_w - 300, y + (total_h - amount_fit.height) // 2 - 4, GREEN, align="right", box_width=300)
    accent_bar(canvas, MARGIN, number_y - 6, title_bottom + 2)
    footer(draw, index, total, dark=False)
    return canvas


def render_verdict(slide: VerdictSlide, index: int, total: int) -> Image.Image:
    canvas = _dark_canvas()
    draw = ImageDraw.Draw(canvas)
    brand_row(canvas, draw, 176, dark=True)
    text_x = MARGIN + 44
    text_w = W - text_x - MARGIN
    kicker_face = font("Bold", 30)
    body = fit(draw, slide.body, "Semibold", text_w, 520, 58, 36, leading=1.22, max_lines=9)
    block_h = 66 + body.height + 70 + 76
    kicker_y = 320 + (1200 - 320 - block_h) // 2
    tracked_text(draw, (text_x, kicker_y), "PRACTICAL VERDICT", kicker_face, MINT, 7)
    body_bottom = draw_lines(draw, body, text_x, kicker_y + 66, WHITE)
    accent_bar(canvas, MARGIN, kicker_y - 6, body_bottom + 2)

    # CTA pill
    pill_face = font("Semibold", 32)
    pill_w = text_width(draw, slide.cta, pill_face) + 80
    pill_y = body_bottom + 70
    draw.rounded_rectangle((text_x, pill_y, text_x + pill_w, pill_y + 76), radius=38, fill=GREEN)
    draw.text((text_x + 40, pill_y + 18), slide.cta, font=pill_face, fill=WHITE)
    site_face = font("Medium", 30)
    draw.text((text_x + pill_w + 28, pill_y + 20), "practicalrewards.com", font=site_face, fill=CLOUD)
    footer(draw, index, total, dark=True)
    return canvas


def render_og(cover: Cover) -> Image.Image:
    width, height = 1200, 630
    canvas = diagonal_gradient(width, height, SLATE)
    card_texture(canvas, alpha=4)
    draw = ImageDraw.Draw(canvas)
    margin = 72
    mark = Image.open(MARK).convert("RGBA").resize((44, 44), Image.Resampling.LANCZOS)
    canvas.paste(mark, (margin, 56), mark)
    draw.text((margin + 58, 60), "Practical Rewards", font=font("Semibold", 28), fill=WHITE)

    text_x = margin + 34
    art = load_card_art(cover.card_art, 330)
    text_w = (width - text_x - margin - 360) if art is not None else (width - text_x - margin)
    kicker_y = 172
    tracked_text(draw, (text_x, kicker_y), cover.kicker.upper(), font("Bold", 22), MINT, 5)
    stat = fit(draw, cover.stat, "Black", text_w, 170, 150, 64, leading=1.0, max_lines=1, step=6)
    bbox = draw.textbbox((0, 0), cover.stat, font=stat.face)
    stat_y = kicker_y + 46
    draw.text((text_x - bbox[0], stat_y - bbox[1]), cover.stat, font=stat.face, fill=WHITE)
    stat_bottom = stat_y + (bbox[3] - bbox[1])
    label = fit(draw, cover.label, "Medium", text_w, 120, 34, 24, leading=1.22, max_lines=3)
    label_bottom = draw_lines(draw, label, text_x, stat_bottom + 26, CLOUD)
    accent_bar(canvas, margin, kicker_y - 4, min(label_bottom + 4, height - 60), width=8)
    if art is not None:
        paste_card(canvas, art, (width - margin - 190, 360), angle=-8)
    draw.text((margin, height - 62), "practicalrewards.com", font=font("Medium", 22), fill=CLOUD)
    return canvas


def render_slide(slide: Slide, index: int, total: int) -> Image.Image:
    if isinstance(slide, Cover):
        return render_cover(slide, index, total)
    if isinstance(slide, TextSlide):
        return render_text(slide, index, total)
    if isinstance(slide, MathSlide):
        return render_math(slide, index, total)
    if isinstance(slide, VerdictSlide):
        return render_verdict(slide, index, total)
    raise TypeError(f"unknown slide type {type(slide).__name__}")


def profile_thumb(image: Image.Image) -> Image.Image:
    return image.crop((0, SQUARE_TOP, W, SQUARE_BOTTOM)).resize((360, 360), Image.Resampling.LANCZOS)


def export(slides: list[Slide], out_dir: Path, cover_for_og: Cover | None = None) -> list[Path]:
    """Render every slide to JPEG (Instagram accepts JPEG only) plus QA thumbnails."""
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(slides)
    paths: list[Path] = []
    for position, slide in enumerate(slides, start=1):
        image = render_slide(slide, position, total)
        if image.size != (W, H):
            raise SlideOverflow("slide is not 1080x1350")
        name = "post.jpg" if total == 1 else f"slide-{position:02d}.jpg"
        path = out_dir / name
        image.save(path, "JPEG", quality=92, optimize=True, subsampling=0)
        profile_thumb(image).save(out_dir / name.replace(".jpg", "-profile-thumb.png"), "PNG", optimize=True)
        paths.append(path)
    if cover_for_og is not None:
        render_og(cover_for_og).save(out_dir / "og.png", "PNG", optimize=True)
    return paths
