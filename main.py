"""VELMORA — a travel poster for a place that isn't there.

A vintage-style poster (768 x 1024) for the floating isles of Velmora,
drawn entirely by this program and saved to
$MAKEFUN_OUTPUT_DIR/entry.png (default /output/entry.png).

Everything is pure Python standard library: the PNG bytes are written
by hand (zlib + struct), the picture is painted with a small set of
drawing helpers on an RGB buffer, and the lettering comes from a tiny
5-by-7 bitmap alphabet defined below. Nothing is read from disk and
nothing touches the network, so two runs of this file produce
byte-identical output.

The scene: a low amber sun over a teal sea, drifting isles with pine
trees and a lighthouse, a hot-air balloon crossing the dusk sky, and
one small sailboat heading home.
"""

import math
import os
import struct
import zlib

# ------------------------------------------------------------------- setup
OUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
OUT_PATH = os.path.join(OUT_DIR, "entry.png")

W, H = 768, 1024
SS = 2                      # supersampling: paint big, average down
IW, IH = W * SS, H * SS

def sc(v):
    """Scale a poster coordinate up to internal canvas coordinates."""
    return v * SS

# ----------------------------------------------------------------- palette
PAL = {
    "night":   (16, 20, 54),
    "dusk":    (72, 52, 110),
    "rose":    (198, 96, 86),
    "amber":   (243, 178, 92),
    "glow_a":  (247, 196, 110),
    "glow_b":  (250, 214, 140),
    "sun":     (255, 232, 178),
    "cream":   (255, 243, 214),
    "coral":   (232, 115, 90),
    "ink":     (24, 28, 58),
    "isle":    (30, 42, 74),
    "pine":    (20, 53, 42),
    "sea_hi":  (16, 84, 98),
    "sea_lo":  (6, 38, 58),
    "foam":    (207, 232, 234),
    "beam":    (255, 233, 168),
    "hull":    (20, 38, 63),
    "glint":   (214, 164, 96),
    "shimmer": (46, 120, 138),
}

def mix(c1, c2, t):
    """Blend two RGB triples."""
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(3))

# ------------------------------------------------------------------ canvas
class Surface:
    """An RGB pixel buffer with flat-colour drawing helpers."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.buf = bytearray(width * height * 3)

    def _at(self, x, y):
        return (y * self.w + x) * 3

    def put(self, x, y, colour):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = self._at(x, y)
            self.buf[o:o + 3] = bytes(colour)

    def fill(self, x0, y0, x1, y1, colour):
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.w, x1); y1 = min(self.h, y1)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(colour) * (x1 - x0)
        for y in range(y0, y1):
            o = self._at(x0, y)
            self.buf[o:o + len(row)] = row

    def span(self, x0, x1, y, colour):
        self.fill(x0, y, x1, y + 1, colour)

    def sky(self, y0, y1, stops):
        """Paint a vertical gradient between (y, colour) stops."""
        for y in range(max(0, y0), min(self.h, y1)):
            for i in range(len(stops) - 1):
                ya, ca = stops[i]
                yb, cb = stops[i + 1]
                if ya <= y <= yb and yb > ya:
                    self.span(0, self.w, y, mix(ca, cb, (y - ya) / (yb - ya)))
                    break
            else:
                self.span(0, self.w, y, stops[-1][1])

    def disc(self, cx, cy, r, colour):
        for dy in range(-r, r + 1):
            half = int(math.sqrt(max(0, r * r - dy * dy)))
            self.span(cx - half, cx + half + 1, cy + dy, colour)

    def oval(self, cx, cy, rx, ry, colour):
        for dy in range(-ry, ry + 1):
            frac = 1.0 - (dy * dy) / float(ry * ry)
            half = int(rx * math.sqrt(max(0.0, frac)))
            self.span(cx - half, cx + half + 1, cy + dy, colour)

    def fill_poly(self, pts, colour):
        """Scanline fill for a simple polygon given as (x, y) pairs."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            hits = []
            for i in range(len(pts)):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % len(pts)]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    hits.append(int(x0 + (y - y0) / float(y1 - y0) * (x1 - x0)))
            hits.sort()
            for i in range(0, len(hits) - 1, 2):
                self.span(hits[i], hits[i + 1] + 1, y, colour)

    def segment(self, x0, y0, x1, y1, colour, width=1):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            t = i / float(steps)
            x = int(round(x0 + (x1 - x0) * t))
            y = int(round(y0 + (y1 - y0) * t))
            self.fill(x - width // 2, y - width // 2,
                      x + width // 2 + 1, y + width // 2 + 1, colour)

    def diamond(self, cx, cy, r, colour):
        self.fill_poly([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                       colour)

# ------------------------------------------------------------ fixed random
class Rng:
    """Deterministic linear-congruential generator (fixed seed)."""

    def __init__(self, seed):
        self.state = seed & 0x7FFFFFFF

    def below(self, n):
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state % n

# -------------------------------------------------------------- bitmap type
# A hand-drawn 5-wide, 7-tall alphabet. "#" is ink, " " is empty.
FONT = {
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "),
    "C": (" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "),
    "D": ("#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "F": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "),
    "G": (" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ### "),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": (" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "J": ("  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"),
    "S": (" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"),
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"),
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
    "-": ("     ", "     ", "     ", "#####", "     ", "     ", "     "),
    ".": ("     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "),
}

def blit_text(cv, text, x, y, scale, colour):
    """Stamp bitmap text onto the canvas; returns the drawn width."""
    cx = x
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        for row in range(7):
            for col in range(5):
                if glyph[row][col] == "#":
                    cv.fill(cx + col * scale, y + row * scale,
                            cx + (col + 1) * scale, y + (row + 1) * scale,
                            colour)
        cx += 6 * scale
    return cx - x - scale

def text_w(text, scale):
    return len(text) * 6 * scale - scale

# ------------------------------------------------------------------- scene
def build_poster():
    cv = Surface(IW, IH)
    rng = Rng(20261121)
    P = PAL

    # --- dusk sky, deep indigo at the top warming to amber at the sea.
    cv.sky(0, sc(620), [
        (0, P["night"]),
        (sc(280), P["dusk"]),
        (sc(470), P["rose"]),
        (sc(620), P["amber"]),
    ])

    # --- stars scattered through the upper sky.
    for _ in range(90):
        x = 30 + rng.below(W - 60)
        y = 30 + rng.below(360)
        r = 1 + rng.below(2)
        tone = 200 + rng.below(56)
        cv.disc(sc(x), sc(y), sc(r), (tone, tone, min(255, tone + 20)))
        if rng.below(5) == 0:  # a few four-point sparkles
            cv.segment(sc(x - 4), sc(y), sc(x + 4), sc(y), (tone, tone, 240), sc(1))
            cv.segment(sc(x), sc(y - 4), sc(x), sc(y + 4), (tone, tone, 240), sc(1))

    # --- low amber sun, left of centre, with a soft glow. It sits low
    # enough that its lower half shows beneath the great isle.
    cv.disc(sc(200), sc(585), sc(150), P["glow_a"])
    cv.disc(sc(200), sc(585), sc(115), P["glow_b"])
    cv.disc(sc(200), sc(585), sc(85), P["sun"])

    # --- crescent moon, upper right.
    cv.disc(sc(640), sc(120), sc(30), P["cream"])
    cv.disc(sc(654), sc(110), sc(26), (64, 52, 96))

    # --- a hot-air balloon drifting across the dusk sky.
    cv.oval(sc(600), sc(300), sc(46), sc(54), P["coral"])
    cv.segment(sc(588), sc(352), sc(592), sc(372), P["ink"], sc(2))
    cv.segment(sc(612), sc(352), sc(608), sc(372), P["ink"], sc(2))
    cv.fill(sc(588), sc(372), sc(612), sc(390), P["hull"])
    cv.segment(sc(600), sc(300), sc(600), sc(352), P["cream"], sc(2))

    # --- birds: six shallow chevrons in the sky.
    for bx, by in [(150, 220), (205, 180), (330, 250), (470, 200), (520, 160), (390, 300)]:
        cv.segment(sc(bx - 10), sc(by), sc(bx), sc(by + 7), P["ink"], sc(2))
        cv.segment(sc(bx), sc(by + 7), sc(bx + 10), sc(by), P["ink"], sc(2))

    # --- the sea: teal, deepening toward the bottom edge.
    cv.sky(sc(620), IH, [
        (sc(620), P["sea_hi"]),
        (IH, P["sea_lo"]),
    ])

    # --- gold glitter on the water beneath the sun.
    for _ in range(26):
        x = 120 + rng.below(200)
        y = 640 + rng.below(300)
        w = 18 + rng.below(46)
        cv.fill(sc(x), sc(y), sc(x + w), sc(y + 3), P["glint"])

    # --- pale teal shimmer scattered across the rest of the water.
    for _ in range(70):
        x = 40 + rng.below(W - 90)
        y = 660 + rng.below(320)
        w = 12 + rng.below(40)
        cv.fill(sc(x), sc(y), sc(x + w), sc(y + 2), P["shimmer"])

    # --- the great drifting isle, centre-left: a flat top that tapers
    # to a point underneath, with pines and a lighthouse on top.
    isle = [(110, 470), (190, 430), (300, 418), (380, 445), (395, 480),
            (360, 540), (300, 585), (250, 600), (210, 565), (150, 540),
            (105, 510)]
    cv.fill_poly([(sc(x), sc(y)) for x, y in isle], P["isle"])
    for tx, ty, th in [(160, 428, 36), (235, 418, 44), (305, 428, 34)]:
        cv.fill_poly([(sc(tx - 16), sc(ty)), (sc(tx), sc(ty - th)),
                      (sc(tx + 16), sc(ty))], P["pine"])
    # lighthouse: cream tower, dark cap, and a narrow beam sweeping left.
    cv.fill(sc(350), sc(380), sc(364), sc(420), P["cream"])
    cv.fill_poly([(sc(346), sc(380)), (sc(368), sc(380)), (sc(357), sc(366))],
                 P["ink"])
    cv.fill_poly([(sc(350), sc(388)), (sc(150), sc(376)), (sc(150), sc(398))],
                 P["beam"])
    cv.disc(sc(357), sc(388), sc(5), P["sun"])

    # --- the smaller isle, right, tapering to a point with a waterfall
    # spilling from its tip into the sea.
    small = [(545, 505), (610, 480), (690, 498), (700, 535),
             (665, 570), (625, 588), (590, 560), (555, 535)]
    cv.fill_poly([(sc(x), sc(y)) for x, y in small], P["isle"])
    cv.fill_poly([(sc(612), sc(500)), (sc(600), sc(472)), (sc(624), sc(472))],
                 P["pine"])
    for k in range(46):  # the fall, leaning gently as it drops
        y = 588 + k
        x = 625 + int(6 * math.sin(k / 9.0))
        cv.fill(sc(x - 5), sc(y), sc(x + 5), sc(y + 1), P["foam"])
    cv.oval(sc(627), sc(640), sc(26), sc(7), P["foam"])

    # --- a distant islet with a single tree, centre frame.
    cv.fill_poly([(sc(440), sc(560)), (sc(470), sc(545)), (sc(510), sc(560)),
                  (sc(495), sc(580)), (sc(470), sc(592)), (sc(450), sc(580))],
                 P["isle"])
    cv.fill_poly([(sc(462), sc(548)), (sc(470), sc(524)), (sc(478), sc(548))],
                 P["pine"])

    # --- one small sailboat heading home, lower right.
    cv.fill_poly([(sc(560), sc(830)), (sc(600), sc(830)), (sc(590), sc(848)),
                  (sc(568), sc(848))], P["hull"])
    cv.segment(sc(580), sc(830), sc(580), sc(778), P["ink"], sc(2))
    cv.fill_poly([(sc(582), sc(782)), (sc(582), sc(828)), (sc(608), sc(828))],
                 P["cream"])
    cv.fill_poly([(sc(578), sc(790)), (sc(578), sc(828)), (sc(558), sc(828))],
                 P["cream"])
    cv.oval(sc(580), sc(854), sc(30), sc(4), (120, 170, 180))

    # --- double cream frame.
    for inset, width in [(16, 5), (28, 2)]:
        i, w = sc(inset), sc(width)
        cv.fill(i, i, IW - i, i + w, P["cream"])
        cv.fill(i, IH - i - w, IW - i, IH - i, P["cream"])
        cv.fill(i, i, i + w, IH - i, P["cream"])
        cv.fill(IW - i - w, i, IW - i, IH - i, P["cream"])

    # --- the place name, big and legible, with a soft shadow. Text is
    # drawn in internal canvas coordinates, so sizes scale by SS too.
    name = "VELMORA"
    scale = 9 * SS
    tw = text_w(name, scale)
    tx = (IW - tw) // 2
    ty = sc(92)
    blit_text(cv, name, tx + 6, ty + 8, scale, P["ink"])
    blit_text(cv, name, tx, ty, scale, P["cream"])
    # a thin rule, two diamonds, and the tagline beneath the name
    cv.fill(sc(tx // SS - 10), sc(168), sc(tx // SS + tw // SS + 10), sc(171),
            P["cream"])
    for dx in (tx // SS - 34, tx // SS + tw // SS + 34):
        cv.diamond(sc(dx), sc(169), sc(7), P["cream"])
    tag = "THE ISLES THAT DRIFT"
    tscale = 4 * SS
    ttw = text_w(tag, tscale)
    blit_text(cv, tag, (IW - ttw) // 2, sc(192), tscale, P["cream"])

    # --- small line at the foot of the poster.
    foot = "SAIL THE SKY - NO MAP REQUIRED"
    fscale = 3 * SS
    ftw = text_w(foot, fscale)
    blit_text(cv, foot, (IW - ftw) // 2, sc(948), fscale, P["cream"])

    return cv

def shrink(cv):
    """Average each SS x SS block of the big canvas into final pixels."""
    out = bytearray(W * H * 3)
    for y in range(H):
        for x in range(W):
            acc = [0, 0, 0]
            for dy in range(SS):
                base = ((y * SS + dy) * IW + x * SS) * 3
                for dx in range(SS):
                    o = base + dx * 3
                    acc[0] += cv.buf[o]
                    acc[1] += cv.buf[o + 1]
                    acc[2] += cv.buf[o + 2]
            o = (y * W + x) * 3
            n = SS * SS
            out[o] = (acc[0] + n // 2) // n
            out[o + 1] = (acc[1] + n // 2) // n
            out[o + 2] = (acc[2] + n // 2) // n
    return bytes(out)

def to_png(rgb, width, height):
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
    data = to_png(shrink(build_poster()), W, H)
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes, %dx%d)" % (OUT_PATH, len(data), W, H))

if __name__ == "__main__":
    main()
