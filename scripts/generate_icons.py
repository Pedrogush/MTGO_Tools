"""Generate pixel-art battle-hammer application icons (.ico) for MTGO Tools.

The hammer is a big-headed maul with a square striking face and a wrapped
handle, drawn on a small grid and upscaled with nearest-neighbour so it stays
crisply pixelated at every icon size. Inspired by the silhouette of a colossal
maul (oversized blocky head, straight handle) without copying any specific art.

Run:  python scripts/generate_icons.py
Output: assets/icons/hammer_<variant>.ico  (+ _preview.png for each)
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image

# Icon sizes to embed. All are integer multiples of the 16px grid so every
# frame upscales to uniform, crisp pixels.
SIZES = [16, 32, 48, 64, 128, 256]

# --- Pixel layout -----------------------------------------------------------
# Legend:
#   .  transparent      #  outline (darkest)
#   L  metal highlight  M  metal mid        S  metal shadow
#   |  handle wood      =  metal band (collar / grip wrap)
STANDARD = [
    "................",
    "..##########....",
    "..#LLMMMMSS#....",
    "..#LLMMMMSS#....",
    "..#LLMMMMSS#....",
    "..#LLMMMMSS#....",
    "..##########....",
    "....#====#......",
    ".....#||#.......",
    ".....#||#.......",
    ".....#||#.......",
    ".....#==#.......",
    ".....#||#.......",
    ".....#||#.......",
    ".....#||#.......",
    ".....####.......",
]

# A heavier, oversized head ("colossus") on a stubbier handle.
COLOSSUS = [
    ".##############.",
    ".#LLLMMMMMMSSS#.",
    ".#LLLMMMMMMSSS#.",
    ".#LLLMMMMMMSSS#.",
    ".#LLLMMMMMMSSS#.",
    ".#LLLMMMMMMSSS#.",
    ".#LLLMMMMMMSSS#.",
    ".##############.",
    "....#======#....",
    ".....#||||#.....",
    ".....#||||#.....",
    ".....#====#.....",
    ".....#||||#.....",
    ".....#||||#.....",
    ".....#||||#.....",
    ".....######.....",
]

OUTLINE = (24, 22, 30, 255)
WOOD = (122, 82, 46, 255)
WOOD_DARK = (150, 150, 162, 255)  # metal band '='
TRANSPARENT = (0, 0, 0, 0)

# Per-variant head palette: (highlight, mid, shadow)
VARIANTS = {
    "iron": ((212, 218, 230), (150, 158, 172), (92, 98, 114)),
    "gold": ((255, 226, 120), (222, 170, 52), (150, 108, 28)),
    "crimson": ((224, 96, 84), (168, 46, 46), (96, 26, 32)),
    "ember": ((250, 196, 92), (214, 108, 40), (120, 44, 30)),
}


def render_grid(grid: list[str], head: tuple) -> Image.Image:
    light, mid, shadow = head
    colors = {
        ".": TRANSPARENT,
        "#": OUTLINE,
        "L": light + (255,),
        "M": mid + (255,),
        "S": shadow + (255,),
        "|": WOOD,
        "=": WOOD_DARK,
    }
    h = len(grid)
    w = len(grid[0])
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            px[x, y] = colors[ch]
    return img


def tilt_ccw45(img: Image.Image) -> Image.Image:
    """Rotate 45 degrees counter-clockwise, kept at the grid resolution.

    Rotating with nearest-neighbour at the small grid size (rather than after
    upscaling) keeps the pixels chunky through the rotation, so the later
    upscale to icon sizes stays crisply pixelated instead of blurring the
    diagonal edges. The result is padded to a square so icon frames stay square.
    """
    rot = img.rotate(45, resample=Image.NEAREST, expand=True)
    side = max(rot.size)
    canvas = Image.new("RGBA", (side, side), TRANSPARENT)
    canvas.paste(rot, ((side - rot.width) // 2, (side - rot.height) // 2))
    return canvas


def build_ico(base: Image.Image, sizes: list[int], path: Path) -> None:
    """Assemble a multi-size .ico from nearest-neighbour-upscaled PNG frames."""
    frames = []
    for s in sizes:
        frame = base.resize((s, s), Image.NEAREST)
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        frames.append((s, buf.getvalue()))

    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(frames)))  # ICONDIR
    offset = 6 + 16 * len(frames)
    for s, data in frames:
        dim = 0 if s >= 256 else s  # 0 means 256 in the ICO directory
        out.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _s, data in frames:
        out.write(data)
    path.write_bytes(out.getvalue())


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "assets" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    shapes = {"": STANDARD, "colossus": COLOSSUS}
    made = []
    for variant, head in VARIANTS.items():
        for shape_name, grid in shapes.items():
            base = tilt_ccw45(render_grid(grid, head))
            name = f"hammer_{variant}" + (f"_{shape_name}" if shape_name else "")
            build_ico(base, SIZES, out_dir / f"{name}.ico")
            # A large crisp preview for quick visual review.
            base.resize((256, 256), Image.NEAREST).save(out_dir / f"{name}_preview.png")
            made.append(name)

    print(f"Wrote {len(made)} icon(s) to {out_dir}:")
    for name in made:
        print(f"  {name}.ico")


if __name__ == "__main__":
    main()
