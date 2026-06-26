#!/usr/bin/env python3
"""Regenerate the raster favicons from web/public/bayesify-favicon.svg.

The SVG (a rounded brand-purple tile + the white swirl mark) is the source of truth; this renders it
to the PNG/ICO sizes browsers and OSes ask for. The rasters are **full-bleed** purple squares (the
rounded corners are filled in) so iOS/Android home-screen icons mask cleanly; the SVG keeps its
rounded corners for the browser tab.

No project dependency — cairosvg + pillow are pulled into an ephemeral pixi env:

    pixi exec --spec cairosvg --spec pillow python web/scripts/gen-favicons.py
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

PUBLIC = Path(__file__).resolve().parents[1] / "public"
SVG = PUBLIC / "bayesify-favicon.svg"
PURPLE = (48, 16, 78, 255)  # #30104e — the brand ink behind the white mark

# name -> pixel size. android-chrome/apple-touch double as the PWA + home-screen icons.
PNGS = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "apple-touch-icon.png": 180,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}


def render(size: int) -> Image.Image:
    """The SVG at `size`px, composited onto a solid purple square (corners filled, no transparency)."""
    png = cairosvg.svg2png(url=str(SVG), output_width=size, output_height=size)
    tile = Image.open(io.BytesIO(png)).convert("RGBA")
    square = Image.new("RGBA", (size, size), PURPLE)
    square.alpha_composite(tile)
    return square


def main() -> None:
    for name, size in PNGS.items():
        render(size).save(PUBLIC / name)
        print("wrote", name)
    # A multi-resolution .ico from one crisp render (legacy browsers / Windows).
    render(256).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote favicon.ico")


if __name__ == "__main__":
    main()
