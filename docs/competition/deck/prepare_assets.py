#!/usr/bin/env python3
"""Turn the generated artwork in `vibe_images/` into the committed assets in `assets/`.

    C:/Users/alois/deck-venv/Scripts/python.exe docs/competition/deck/prepare_assets.py

The four backdrops are smooth line art with no text in them, so they are re-encoded as
quality-88 JPEGs: same look on a projector, roughly a fifth of the bytes in the .pptx.
The icon sheet is one 4x3 grid, so each cell is auto-trimmed to its own glyph, padded to
a square, resampled to 256 px and given a transparent background, which lets a chip sit
behind an icon without a white box showing.

`vibe_images/` is scratch output from the image generator and is not part of the repository.
`build_deck.py` reads only `assets/`, so a rebuild works whether or not the originals are
still on disk. Re-run this script only when the artwork itself changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
RAW = HERE.parent.parent.parent / "vibe_images"
OUT = HERE / "assets"
ICONS = OUT / "icons"

BACKDROPS = [
    ("cover-bg", "cover-bg.jpg"),
    ("divider-bg", "divider-bg.jpg"),
    ("closing-bg", "closing-bg.jpg"),
    ("blueprint-wash", "blueprint.jpg"),
]

GRID = (4, 3)          # columns, rows
ICON_PX = 256

# reading order of the generated sheet: left to right, then top to bottom
ICON_NAMES = [
    "cloud", "clock", "topology", "research",
    "shield", "terminal", "ledger", "chain",
    "telegram", "gauge", "lock", "git",
]


def newest(prefix: str) -> Path | None:
    if not RAW.is_dir():
        return None
    hits = sorted(RAW.glob(f"{prefix}_*.png"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def backdrop() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for prefix, name in BACKDROPS:
        src = newest(prefix)
        if src is None:
            print(f"  skip {name}: no {prefix}_*.png in vibe_images")
            continue
        im = Image.open(src).convert("RGB")
        im.save(OUT / name, "JPEG", quality=88, optimize=True, progressive=True)
        print(f"  {name:16} {im.size[0]}x{im.size[1]}  "
              f"{(OUT / name).stat().st_size / 1024:.0f} KB")


def cell_crop(arr, x0: int, y0: int, x1: int, y1: int):
    """Tight box of the glyph in one cell, plus that cell's own background level.

    The sheet's white sits near 245 and drifts a few levels across the frame, so the
    background is measured inside the cell instead of assumed. Keying against a hard 255
    turns that drift into a grey haze, and the faintest drift bands go opaque black.
    """
    lum = np.asarray(Image.fromarray(arr[y0:y1, x0:x1]).convert("L"), dtype=float)
    wp = float(np.percentile(lum, 70))
    ink = lum < wp - 14
    if not ink.any():
        return None, wp
    ys, xs = np.nonzero(ink)
    return (x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1), wp


def icons() -> None:
    src = newest("icon-sheet")
    if src is None:
        print("  skip icons: no icon-sheet_*.png in vibe_images")
        return
    arr = np.asarray(Image.open(src).convert("RGB"))
    cw, ch = arr.shape[1] // GRID[0], arr.shape[0] // GRID[1]
    ICONS.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(ICON_NAMES):
        col, row = i % GRID[0], i // GRID[0]
        x0, y0 = col * cw, row * ch
        bbox, wp = cell_crop(arr, x0 + 6, y0 + 6, x0 + cw - 6, y0 + ch - 6)
        if bbox is None:
            print(f"  {name:10} EMPTY CELL - check the sheet grid")
            continue
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        side = max(w, h) * 1.16                       # keep a hairline of padding all round
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        sq = (int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2))
        glyph = Image.fromarray(arr[sq[1]:sq[3], sq[0]:sq[2]]).resize(
            (ICON_PX, ICON_PX), Image.LANCZOS)

        # alpha ramps from the measured background down to the stroke, so edges stay smooth
        lum = np.asarray(glyph.convert("L"), dtype=float)
        alpha = np.clip((wp - lum) * 255.0 / max(28.0, wp * 0.20), 0, 255).astype("uint8")
        glyph = glyph.convert("RGBA")
        glyph.putalpha(Image.fromarray(alpha))
        glyph.save(ICONS / f"{name}.png", "PNG", optimize=True)
        print(f"  {name:10} {ICON_PX}x{ICON_PX}  "
              f"{(ICONS / f'{name}.png').stat().st_size / 1024:.0f} KB  "
              f"glyph {w}x{h}  white {wp:.0f}")


def main() -> int:
    print(f"sources: {RAW} ({'found' if RAW.is_dir() else 'missing - assets unchanged'})")
    print("backdrops:")
    backdrop()
    print("icons:")
    icons()
    return 0


if __name__ == "__main__":
    sys.exit(main())
