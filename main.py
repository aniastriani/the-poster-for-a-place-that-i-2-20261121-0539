"""Velmora — a travel poster for a place that does not exist.

Draws one vintage-style travel poster (768x1024) and writes it to
$MAKEFUN_OUTPUT_DIR/entry.png (default /output/entry.png).

The poster is painted entirely with code: a hand-rolled PNG writer
(zlib + struct, no third-party libraries), a small canvas of drawing
primitives (gradients, polygons, discs, lines), and a tiny 5x7 bitmap
letter set for the place name. Nothing is read from disk, nothing is
fetched from the network, and every number is a fixed constant, so
every run produces byte-identical output.

The place: VELMORA, the isles that drift — floating islands above a
teal sea, a low gold sun, a crescent moon, a lighthouse, and one small
sailboat on its way home.
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------- output
OUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
OUT_PATH = os.path.join(OUT_DIR, "entry.png")

W, H = 768, 1024          # final poster size
SS = 2                    # supersample factor; drawn big, then averaged down
IW, IH = W * SS, H * SS   # internal canvas size


def s(v):
    """Scale a final-coordinate value to internal coordinates."""
    return v * SS


# ---------------------------------------------------------------- palette
INK = (24, 28, 58)            # deep indigo, outlines and shadow
CREAM = (255, 243, 214)       # poster cream: frame, lettering, sails
GOLD = (242, 180, 92)         # horizon gold
SUN = (255, 233, 184)         # sun disc
CORAL = (232, 115, 90)        # sunset coral
VIOLET = (122, 78, 140)       # dusk violet
INDIGO = (30, 36, 71)         # night-sky top
ISLE = (30, 42, 74)           # island silhouette
PINE = (20, 53, 42)           # pine green
SEA_TOP = (14, 74, 90)        # sea at the horizon
SEA_DEEP = (7, 42, 61)        # sea at the bottom edge
FOAM = (207, 232, 234)        # waterfall foam
BEAM = (255, 233, 168)        # lighthouse beam
HULL = (20, 38, 63)           # sailboat hull


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ---------------------------------------------------------------- canvas
class Canvas:
    """A plain RGB canvas with a few flat-colour drawing primitives."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.px = bytearray(width * height * 3)

    def _off(self, x, y):
        return (y * self.w + x) * 3

    def dot(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = self._off(x, y)
            self.px[o:o + 3] = bytes(color)

    def rect(self, x0, y0, x1, y1, color):
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w, x1)
        y1 = min(self.h, y1)
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            o = self._off(x0, y)
            self.px[o:o + len(row)] = row

    def hspan(self, x0, x1, y, color):
        if y < 0 or y >= self.h:
            return
        self.rect(x0, y, x1, y + 1, color)

    def vgrad(self, y0, y1, stops):
        """Vertical gradient; stops is a list of (y, color) pairs."""
        for y in range(max(0, y0), min(self.h, y1)):
            for i in range(len(stops) - 1):
                ya, ca = stops[i]
                yb, cb = stops[i + 1]
                if ya <= y <= yb and yb > ya:
                    self.hspan(0, self.w, y, lerp(ca, cb, (y - ya) / (yb - ya)))
                    break
            else:
                self.hspan(0, self.w, y, stops[-1][1])

    def disc(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.hspan(cx - dx, cx + dx + 1, cy + dy, color)

    def ellipse(self, cx, cy, rx, ry, color):
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            dx = int(rx * math.sqrt(max(0.0, t)))
            self.hspan(cx - dx, cx + dx + 1, cy + dy, color)

    def poly(self, points, color):
        """Scanline-filled polygon; points are (x, y) pairs."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            for i in range(len(points)):
                x0, y0 = points[i]
                x1, y1 = points[(i + 1) % len(points)]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y - y0) / float(y1 - y0)
                    xs.append(int(x0 + t * (x1 - x0)))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hspan(xs[i], xs[i + 1] + 1, y, color)

    def line(self, x0, y0, x1, y1, color, width=1):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            t = i / float(steps)
            x = int(round(x0 + (x1 - x0) * t))
            y = int(round(y0 + (y1 - y0) * t))
            self.rect(x - width // 2, y - width // 2,
                      x + width // 2 + 1, y + width // 2 + 1, color)

    def ring(self, cx, cy, r, color, width=1):
        for dy in range(-r - width, r + width + 1):
            for dx in range(-r - width, r + width + 1):
                d = math.sqrt(dx * dx + dy * dy)
                if r - width <= d <= r + width:
                    self.dot(cx + dx, cy + dy, color)


# ------------------------------------------------------- deterministic dice
class Dice:
    """A tiny fixed-seed generator; the poster never changes between runs."""

    def __init__(self, seed):
        self.state = seed & 0x7FFFFFFF

    def next(self, n):
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state % n


# ------------------------------------------------------------- bitmap font
# 5x7 letters, drawn from '#' rows. Only the letters VELMORA are needed.
GLYPHS = {
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "R": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#   #"),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
}


def draw_text(cv, text, x, y, scale, color):
    """Draw text with the bitmap font; returns the width in pixels."""
    cx = x
    for ch in text:
        glyph = GLYPHS.get(ch, GLYPHS[" "])
        for row in range(7):
            for col in range(5):
                if glyph[row][col] == "#":
                    cv.rect(cx + col * scale, y + row * scale,
                            cx + (col + 1) * scale, y + (row + 1) * scale,
                            color)
        cx += 6 * scale
    return cx - x - scale


def text_width(text, scale):
    return len(text) * 6 * scale - scale


# ------------------------------------------------------------------ poster
def paint():
    cv = Canvas(IW, IH)
    dice = Dice(20261121)

    # --- sky: indigo at the top, violet, coral, gold at the horizon.
    cv.vgrad(0, s(640), [
        (0, INDIGO),
        (s(300), VIOLET),
        (s(480), CORAL),
        (s(640), GOLD),
    ])

    # --- stars in the upper sky.
    for _ in range(110):
        x = 30 + dice.next(W - 60)
        y = 40 + dice.next(420)
        r = 1 + dice.next(2)
        tone = 200 + dice.next(56)
        cv.disc(s(x), s(y), s(r), (tone, tone, min(255, tone + 20)))
        if dice.next(5) == 0:  # a few four-point sparkles
            cv.line(s(x - 4), s(y), s(x + 4), s(y), (tone, tone, 240), s(1))
            cv.line(s(x), s(y - 4), s(x), s(y + 4), (tone, tone, 240), s(1))

    # --- low sun with a warm glow, sitting just right of centre.
    cv.disc(s(470), s(600), s(150), (247, 200, 115))
    cv.disc(s(470), s(600), s(118), (249, 211, 138))
    cv.disc(s(470), s(600), s(88), SUN)

    # --- crescent moon, upper right.
    cv.disc(s(636), s(128), s(34), CREAM)
    cv.disc(s(650), s(118), s(30), (64, 52, 96))

    # --- birds: five small shallow chevrons in the sky.
    for bx, by in [(180, 250), (240, 210), (560, 300), (610, 260), (300, 330)]:
        cv.line(s(bx - 10), s(by), s(bx), s(by + 7), INK, s(2))
        cv.line(s(bx), s(by + 7), s(bx + 10), s(by), INK, s(2))

    # --- sea: teal gradient from the horizon to the bottom edge.
    cv.vgrad(s(640), IH, [
        (s(640), SEA_TOP),
        (IH, SEA_DEEP),
    ])

    # --- sun glitter on the water: short gold dashes under the sun.
    for i in range(26):
        x = 380 + dice.next(190)
        y = 660 + dice.next(300)
        w = 18 + dice.next(46)
        cv.rect(s(x), s(y), s(x + w), s(y + 3), (214, 164, 96))

    # --- sea shimmer: pale teal dashes scattered across the water.
    for _ in range(70):
        x = 40 + dice.next(W - 90)
        y = 680 + dice.next(300)
        w = 12 + dice.next(40)
        cv.rect(s(x), s(y), s(x + w), s(y + 2), (46, 120, 138))

    # --- the great floating isle, left of centre, with pines and a light.
    isle = [(70, 470), (150, 430), (260, 415), (360, 440), (400, 480),
            (385, 545), (340, 600), (300, 615), (250, 590), (190, 600),
            (120, 570), (80, 520)]
    cv.poly([(s(x), s(y)) for x, y in isle], ISLE)
    for tx, ty, th in [(150, 428, 26), (215, 422, 32), (285, 426, 24)]:
        cv.poly([(s(tx - 14), s(ty)), (s(tx), s(ty - th)),
                 (s(tx + 14), s(ty))], PINE)
    # lighthouse: cream tower, dark cap, and a beam reaching right.
    cv.rect(s(322), s(392), s(336), s(432), CREAM)
    cv.poly([(s(318), s(392)), (s(340), s(392)), (s(329), s(378))], INK)
    cv.poly([(s(336), s(402)), (s(560), s(360)), (s(560), s(420))], BEAM)
    cv.disc(s(329), s(400), s(5), SUN)

    # --- the smaller isle, right, with a waterfall spilling into the sea.
    small = [(540, 520), (600, 495), (680, 510), (700, 550),
             (665, 585), (600, 595), (560, 560)]
    cv.poly([(s(x), s(y)) for x, y in small], ISLE)
    cv.poly([(s(612), s(500)), (s(600), s(472)), (s(624), s(472))], PINE)
    for k in range(46):  # the fall, leaning gently as it drops
        y = 595 + k
        x = 620 + int(6 * math.sin(k / 9.0))
        cv.rect(s(x - 5), s(y), s(x + 5), s(y + 1), FOAM)
    cv.ellipse(s(622), s(644), s(26), s(7), FOAM)

    # --- a distant islet with a single tree, centre frame.
    cv.poly([(s(430), s(560)), (s(470), s(545)), (s(510), s(560)),
             (s(495), s(585)), (s(450), s(585))], ISLE)
    cv.poly([(s(462), s(548)), (s(470), s(524)), (s(478), s(548))], PINE)

    # --- one small sailboat on its way home.
    cv.poly([(s(500), s(800)), (s(540), s(800)), (s(530), s(818)),
             (s(508), s(818))], HULL)
    cv.line(s(520), s(800), s(520), s(748), INK, s(2))
    cv.poly([(s(522), s(752)), (s(522), s(798)), (s(548), s(798))], CREAM)
    cv.poly([(s(518), s(760)), (s(518), s(798)), (s(498), s(798))], CREAM)
    cv.ellipse(s(520), s(824), s(30), s(4), (120, 170, 180))

    # --- double cream frame.
    cv.ring(s(0), s(0), 0, CREAM)  # no-op guard: keeps the frame code below tidy
    for inset, width in [(18, 4), (30, 2)]:
        i, w = s(inset), s(width)
        cv.rect(i, i, IW - i, i + w, CREAM)
        cv.rect(i, IH - i - w, IW - i, IH - i, CREAM)
        cv.rect(i, i, i + w, IH - i, CREAM)
        cv.rect(IW - i - w, i, IW - i, IH - i, CREAM)

    # --- the place name, big and legible, with a soft shadow.
    name = "VELMORA"
    scale = 9
    tw = text_width(name, scale)
    tx = (W - tw) // 2
    ty = 96
    draw_text(cv, name, tx + 3, ty + 4, scale, INK)
    draw_text(cv, name, tx, ty, scale, CREAM)
    # a thin rule and two diamonds beneath the name
    cv.rect(s(tx - 10), s(186), s(tx + tw + 10), s(189), CREAM)
    for dx in (tx - 34, tx + tw + 34):
        cv.poly([(s(dx), s(178)), (s(dx + 7), s(187)),
                 (s(dx), s(196)), (s(dx - 7), s(187))], CREAM)

    return cv


def downsample(cv):
    """Average each 2x2 block of the big canvas into the final pixels."""
    out = bytearray(W * H * 3)
    for y in range(H):
        for x in range(W):
            acc = [0, 0, 0]
            for dy in range(SS):
                base = ((y * SS + dy) * IW + x * SS) * 3
                for dx in range(SS):
                    o = base + dx * 3
                    acc[0] += cv.px[o]
                    acc[1] += cv.px[o + 1]
                    acc[2] += cv.px[o + 2]
            o = (y * W + x) * 3
            out[o] = (acc[0] + 2) // 4
            out[o + 1] = (acc[1] + 2) // 4
            out[o + 2] = (acc[2] + 2) // 4
    return bytes(out)


def png_bytes(rgb, width, height):
    """Encode raw RGB bytes as a PNG (filter 0, zlib level 9)."""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = png_bytes(downsample(paint()), W, H)
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes, %dx%d)" % (OUT_PATH, len(data), W, H))


if __name__ == "__main__":
    main()
