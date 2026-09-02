#!/usr/bin/env python3
"""Render Instagram profile-picture candidates for practical.rewards (1080x1080)."""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import font, diagonal_gradient, vertical_gradient, card_texture, hex_rgb, SLATE, GREEN, GREEN_LIGHT, MINT, GOLD, WHITE, PAPER, INK

SIZE = 1080

def monogram(draw, text, size_px, fill, cy, tracking=-10):
    face = font("Black", size_px)
    # measure with tracking
    widths = [draw.textbbox((0, 0), ch, font=face) for ch in text]
    total = sum(b[2] - b[0] for b in widths) + tracking * (len(text) - 1)
    x = (SIZE - total) // 2
    top = min(b[1] for b in widths); bottom = max(b[3] for b in widths)
    y = cy - (bottom - top) // 2 - top
    for ch, b in zip(text, widths):
        draw.text((x - b[0], y), ch, font=face, fill=fill)
        x += (b[2] - b[0]) + tracking

def circle_mask():
    m = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(m).ellipse((0, 0, SIZE - 1, SIZE - 1), fill=255)
    return m

def variant_a():
    """Forest green disc, gold PR — the favicon, tuned for a circle."""
    img = Image.new("RGB", (SIZE, SIZE), "#047857")
    d = ImageDraw.Draw(img)
    monogram(d, "PR", 520, GOLD, SIZE // 2, tracking=-6)
    return img

def variant_b():
    """Slate gradient with the hero's green accent bar and white PR."""
    img = diagonal_gradient(SIZE, SIZE, SLATE); card_texture(img, alpha=6)
    d = ImageDraw.Draw(img)
    monogram(d, "PR", 480, WHITE, SIZE // 2 + 10, tracking=-6)
    bar = vertical_gradient(26, 400, GREEN, GREEN_LIGHT)
    mask = Image.new("L", bar.size, 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, 25, 399), radius=13, fill=255)
    img.paste(bar, (150, SIZE // 2 - 190), mask)
    return img

def variant_c():
    """Paper disc, forest PR, thin green ring — the light cover style."""
    img = Image.new("RGB", (SIZE, SIZE), PAPER)
    d = ImageDraw.Draw(img)
    d.ellipse((34, 34, SIZE - 34, SIZE - 34), outline=GREEN, width=30)
    monogram(d, "PR", 470, "#065f46", SIZE // 2, tracking=-6)
    return img

def variant_d():
    """Green disc with a subtle card silhouette behind a white PR."""
    img = diagonal_gradient(SIZE, SIZE, ("#065f46", "#059669", "#10b981"))
    d = ImageDraw.Draw(img)
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0)); od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((250, 330, 830, 700), radius=48, fill=(255, 255, 255, 26))
    od.rounded_rectangle((300, 470, 480, 500), radius=10, fill=(255, 255, 255, 40))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))
    d = ImageDraw.Draw(img)
    monogram(d, "PR", 470, WHITE, SIZE // 2 + 14, tracking=-6)
    return img

VARIANTS = {"a-forest-gold": variant_a, "b-slate": variant_b, "c-paper-ring": variant_c, "d-green-card": variant_d}

def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (4 * 300 + 60, 300 + 160 + 40), "#888")
    for i, (name, fn) in enumerate(VARIANTS.items()):
        img = fn(); img.save(out / f"avatar-{name}.png", "PNG", optimize=True)
        circ = Image.new("RGB", (SIZE, SIZE), "#888"); circ.paste(img, (0, 0), circle_mask())
        sheet.paste(circ.resize((280, 280), Image.Resampling.LANCZOS), (20 + i * 300, 20))
        sheet.paste(circ.resize((110, 110), Image.Resampling.LANCZOS), (20 + i * 300, 320))
        sheet.paste(circ.resize((48, 48), Image.Resampling.LANCZOS), (150 + i * 300, 350))
    sheet.save(out / "avatar-sheet.png"); print(out / "avatar-sheet.png")

if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/avatars"))
