"""Regenerate the Equip API favicon binary set (PNG + multi-resolution ICO).

Why binaries when we already serve favicon.svg:

- Browsers cache favicons aggressively across sessions and frequently ignore
  ``Cache-Control: no-cache`` on the favicon path specifically. A stale tab
  that loaded an old SVG can show that old icon for days even after the
  server has been updated.
- iOS home-screen "Add to Home Screen" wants a PNG at apple-touch-icon
  (180x180) — Safari renders SVG apple-touch-icons inconsistently.
- Android PWA install prompts want android-chrome-192x192.png + 512x512.
- Some legacy scrapers (older Vercel project-card screenshot generators,
  internal preview tools) request /favicon.ico expecting an ICO binary
  and silently fall back to a default if they receive an SVG with ``.ico``
  extension. A real multi-resolution ICO (16/32/48 px) eliminates the
  ambiguity.

The Equip API mark: rounded-square deep-sage field (--success #2F7A53),
warm-paper inverse "E" (--background #FAF7F1). Sage backend / violet
frontend pairing differentiates api.equipbible.com from equipbible.com
in browser tab strips and project lists.

Run from the static/ directory::

    python _generate_icons.py

Re-run any time the canonical favicon.svg changes shape. Outputs are
deterministic — same SVG produces byte-identical PNGs, which keeps the
git diff sane.
"""

from PIL import Image, ImageDraw

# Canonical brand colors — keep in sync with backend/app/static/favicon.svg
# (sage on warm paper; the ``--success`` + ``--background`` semantic
# tokens pinned to OKLCH-equivalent hex).
SAGE = "#2F7A53"
PAPER = "#FAF7F1"


def draw_equip_e(size: int) -> Image.Image:
    """Render the Equip "E" mark at the given pixel size on a rounded
    sage square. The 32-px reference SVG uses geometry
    ``rect 9,8 w14 h3`` etc.; we scale proportionally to the requested
    output size and round to pixel boundaries (the SVG corner radius is
    ``rx=7`` at 32 px → ~22% of the side, preserved on each scale)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = size / 32.0  # scale factor; 1.0 at the reference 32x32

    def r(x: float, y: float, w: float, h: float) -> tuple[int, int, int, int]:
        # SVG uses (x, y, width, height); PIL.rectangle wants (x0, y0, x1, y1)
        return (round(x * s), round(y * s), round((x + w) * s), round((y + h) * s))

    # Rounded-square sage field. PIL ≥ 8.2 supports rounded_rectangle.
    radius = round(7 * s)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=SAGE)

    # Inverse "E" — four warm-paper bars matching the SVG.
    draw.rectangle(r(9, 8, 3, 16), fill=PAPER)   # vertical spine
    draw.rectangle(r(9, 8, 14, 3), fill=PAPER)   # top arm
    draw.rectangle(r(9, 15, 11, 3), fill=PAPER)  # middle arm (shorter)
    draw.rectangle(r(9, 21, 14, 3), fill=PAPER)  # bottom arm

    return img


def main() -> None:
    sizes_png = {
        # standard favicons (referenced in head as image/png to give
        # browsers an alternative to the SVG if SVG rendering fails)
        "favicon-16x16.png": 16,
        "favicon-32x32.png": 32,
        # Apple touch icon — iOS home screen
        "apple-touch-icon.png": 180,
        # Android PWA install icons
        "android-chrome-192x192.png": 192,
        "android-chrome-512x512.png": 512,
    }
    for name, size in sizes_png.items():
        img = draw_equip_e(size)
        img.save(name, "PNG", optimize=True)
        print(f"  wrote {name} ({size}x{size})")

    # Multi-resolution ICO so the legacy /favicon.ico path serves a real
    # ICO container instead of an SVG-masquerading-as-ICO.
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    base = draw_equip_e(48)
    base.save("favicon.ico", format="ICO", sizes=ico_sizes)
    print(f"  wrote favicon.ico (multi-resolution: {ico_sizes})")


if __name__ == "__main__":
    main()
