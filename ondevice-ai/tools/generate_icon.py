from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

BASE_SIZE = 1024
ICONSET_NAME = "MAHI.iconset"

ICONSET_SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]

GOOGLE_RED = (234, 67, 53)
GOOGLE_YELLOW = (251, 188, 5)
GOOGLE_GREEN = (52, 168, 83)
GOOGLE_BLUE = (66, 133, 244)
GOOGLE_BLUE_DARK = (26, 115, 232)


def _ribbon_polygon(cx: int, cy: int, width: int, height: int, angle_deg: float, skew: float = 0.0) -> list[tuple[int, int]]:
    """Build a quadrilateral ribbon rotated around the center point."""
    angle = math.radians(angle_deg)
    hw, hh = width / 2.0, height / 2.0
    points = [
        (-hw, -hh),
        (hw, -hh + skew * hh),
        (hw, hh),
        (-hw, hh - skew * hh),
    ]
    rotated = []
    for px, py in points:
        rx = px * math.cos(angle) - py * math.sin(angle)
        ry = px * math.sin(angle) + py * math.cos(angle)
        rotated.append((int(cx + rx), int(cy + ry)))
    return rotated


def _letter_box(x: float, y: float, width: float, height: float) -> tuple[int, int, int, int]:
    return (
        int(x),
        int(y),
        int(x + width),
        int(y + height),
    )


def _draw_letter(draw: ImageDraw.ImageDraw, letter: str, box: tuple[int, int, int, int], color: tuple[int, int, int]) -> None:
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0

    def rect(rx0: float, ry0: float, rx1: float, ry1: float) -> None:
        draw.rectangle(
            (
                x0 + rx0 * w,
                y0 + ry0 * h,
                x0 + rx1 * w,
                y0 + ry1 * h,
            ),
            fill=color,
        )

    def poly(points: list[tuple[float, float]]) -> None:
        draw.polygon([
            (x0 + px * w, y0 + py * h)
            for px, py in points
        ], fill=color)

    if letter == "M":
        rect(0.0, 0.0, 0.22, 1.0)
        rect(0.78, 0.0, 1.0, 1.0)
        poly([(0.22, 0.0), (0.5, 0.45), (0.78, 0.0)])
        poly([(0.22, 1.0), (0.5, 0.55), (0.78, 1.0)])
    elif letter == "A":
        poly([(0.08, 1.0), (0.42, 0.0), (0.58, 0.0), (0.92, 1.0), (0.72, 1.0), (0.6, 0.65), (0.4, 0.65), (0.28, 1.0)])
        rect(0.37, 0.58, 0.63, 0.73)
    elif letter == "H":
        rect(0.05, 0.0, 0.25, 1.0)
        rect(0.75, 0.0, 0.95, 1.0)
        rect(0.25, 0.4, 0.75, 0.6)
    elif letter == "I":
        rect(0.35, 0.0, 0.65, 1.0)
    elif letter == "L":
        rect(0.05, 0.0, 0.25, 1.0)
        rect(0.05, 0.8, 0.95, 1.0)
    elif letter == " ":
        pass
    else:
        rect(0.0, 0.0, 1.0, 1.0)


def _draw_word(draw: ImageDraw.ImageDraw, word: str, start_x: int, baseline_y: int, letter_width: int, letter_height: int, spacing: int, colors: list[tuple[int, int, int]]) -> None:
    x = start_x
    color_iter = iter(colors)
    for char in word:
        box = _letter_box(x, baseline_y - letter_height, letter_width, letter_height)
        if char == " ":
            x += letter_width // 2 + spacing
            continue
        color = next(color_iter, colors[-1])
        _draw_letter(draw, char, box, color)
        x += letter_width + spacing


def build_base_icon(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGBA", (BASE_SIZE, BASE_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # soft background circle
    cx = cy = BASE_SIZE // 2
    radius = int(BASE_SIZE * 0.42)
    for idx in range(40):
        r = radius - idx
        alpha = int(70 * (1 - idx / 40))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, alpha))

    # white background
    draw.rectangle((0, 0, BASE_SIZE, BASE_SIZE), fill=(255, 255, 255, 255))

    # ribbon segments for stylised "M"
    left = _ribbon_polygon(360, 512, 200, 560, -15, skew=0.15)
    right = _ribbon_polygon(664, 512, 200, 560, 15, skew=-0.15)

    apex_width = 360
    apex_height = 240
    apex_left = _ribbon_polygon(460, 340, apex_width, apex_height, -2, skew=0.25)
    apex_right = _ribbon_polygon(564, 340, apex_width, apex_height, 2, skew=-0.25)

    base = _ribbon_polygon(512, 676, 180, 320, 0, skew=0)

    draw.polygon(left, fill=GOOGLE_RED)
    draw.polygon(apex_left, fill=GOOGLE_YELLOW)
    draw.polygon(apex_right, fill=GOOGLE_YELLOW)
    draw.polygon(right, fill=GOOGLE_GREEN)
    draw.polygon(base, fill=GOOGLE_BLUE)

    # Add a subtle white highlight to mimic folded ribbon edges
    highlight = Image.new("RGBA", img.size, (255, 255, 255, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    highlight_draw.line([(282, 220), (512, 620)], fill=(255, 255, 255, 90), width=34)
    highlight_draw.line([(742, 220), (512, 620)], fill=(255, 255, 255, 70), width=34)
    highlight_draw.line([(512, 560), (512, 790)], fill=(255, 255, 255, 60), width=28)
    img = Image.alpha_composite(img, highlight)

    # word mark
    word_colors = [
        GOOGLE_BLUE_DARK,
        GOOGLE_BLUE,
        GOOGLE_RED,
        GOOGLE_YELLOW,
        GOOGLE_RED,
        GOOGLE_GREEN,
        GOOGLE_BLUE,
    ]
    _draw_word(draw, "MAHI LLM", 262, 870, 80, 160, 18, word_colors)

    img.save(output, format="PNG")


def build_iconset(base_png: Path, iconset_dir: Path) -> None:
    base = Image.open(base_png)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    for size, filename in ICONSET_SIZES:
        resized = base.resize((size, size), Image.LANCZOS)
        resized.save(iconset_dir / filename, format="PNG")


def convert_iconset(iconset_dir: Path, target: Path) -> None:
    subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", target], check=True)


def main() -> None:
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    base_png = assets_dir / "icon_base.png"
    iconset_dir = assets_dir / ICONSET_NAME
    icns_path = assets_dir / "icon.icns"

    build_base_icon(base_png)
    build_iconset(base_png, iconset_dir)
    convert_iconset(iconset_dir, icns_path)

    print(f"Generated {icns_path}")


if __name__ == "__main__":
    main()
