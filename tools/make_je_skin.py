#!/usr/bin/env python3
"""The JE-8086 2.0 skin art library: chassis, section panels, knob and fader film strips, rubber keys with LEDs, the green
LCD. Built from gearmulator's JE-8086 skin "jeTrancy" (skin/jeTrancy/, by theusualsuspects, GPL-3.0): its blue chassis, the
JE-8086 wordmark, the 128-frame knob, the rubber buttons with LEDs, the fader caps and its fonts (Metropolis, Vipnagorgialla:
baked into the art only). The rest is drawn here (Pillow). Laid out by tools/skin_pages.py; previews from tools/make_tui.py --preview.

The look: the JP-8000 / JP-8080 panel as jeTrancy draws it, a blue-grey chassis with black section panels, orange section titles
and white print, black knobs with white caps, LED buttons and long faders; the display is a green-on-black LCD.
"""
import math, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JT = os.path.join(ROOT, "skin", "jeTrancy")
PARTS = os.path.join(ROOT, "skin", "parts")
SS = 3

ORANGE = (255, 106, 20)        # jeTrancy's section titles
ORANGE_DIM = (150, 66, 18)
INK = (236, 236, 236)          # white panel print
INK_DIM = (150, 156, 170)
PANEL = (8, 8, 10)             # black section panel
PANEL_EDGE = (40, 46, 62)
LCD_BG = (4, 14, 6)            # green-on-black LCD
LCD_GLASS = (10, 26, 12)
LCD_INK = (70, 255, 110)       # lit segments
LCD_DIM = (22, 60, 30)         # unlit cells / rules
LED_ON = (255, 40, 30)
QLINK = (255, 120, 30)         # MPC focus colour (previews only)

_f = {}


def font(px, face="Metropolis-SemiBold.ttf"):
    k = (int(px), face)
    if k not in _f:
        _f[k] = ImageFont.truetype(os.path.join(JT, face), max(1, int(px)))
    return _f[k]


def title_font(px):
    return font(px, "Vipnagorgialla Rg.ttf")


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


# ---- chassis, panels, print -------------------------------------------------------------------------------------------
def chassis():
    """jeTrancy's blue chassis, 1280 x 628 (skin/parts/bg.png, cut from its background)."""
    return Image.open(os.path.join(PARTS, "bg.png")).convert("RGB")


def wordmark(h):
    w = Image.open(os.path.join(PARTS, "wordmark.png")).convert("RGBA")
    return w.resize((int(w.width * h / w.height), h), Image.LANCZOS)


def section(img, x0, y0, x1, y1, title=None, q=False):
    """A jeTrancy section: a black rounded panel with a thin blue-grey edge, a soft inner shadow and the orange title centred
    at its top (moved right when the block is a Q-Link group, clear of the MPC's Q tag)."""
    d = ImageDraw.Draw(img)
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 2, y0 + 4, x1 + 2, y1 + 5], 9, fill=150)
    img.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(4)))
    d.rounded_rectangle([x0, y0, x1, y1], 9, fill=PANEL, outline=PANEL_EDGE, width=2)
    if title:
        f = title_font(20)
        cx = (x0 + x1) // 2
        tw = d.textlength(title, font=f)
        if q and cx - tw / 2 < x0 + 40:
            cx = int(x0 + 40 + tw / 2)
        d.text((cx, y0 + 6), title, font=f, fill=ORANGE, anchor="ma")


def legend(d, x, y, text, size=15, col=INK, anchor="ma"):
    d.text((x, y), text, font=font(size), fill=col, anchor=anchor)


def bracket(d, x0, x1, y, text, col=INK, size=13):
    """The panel's bracket print over a group of controls (SOLO SW, MORPHING, A D S R): a rule with turned-down ends, the
    caption in a gap at the middle."""
    f = font(size)
    tw = d.textlength(text, font=f)
    cx = (x0 + x1) / 2
    d.line([x0, y, cx - tw / 2 - 6, y], fill=col, width=1)
    d.line([cx + tw / 2 + 6, y, x1, y], fill=col, width=1)
    d.line([x0, y, x0, y + 6], fill=col, width=1)
    d.line([x1, y, x1, y + 6], fill=col, width=1)
    d.text((cx, y), text, font=f, fill=col, anchor="mm")


# ---- knob (jeTrancy's 128-frame film strip, white or red cap) ---------------------------------------------------------
def knob_strip(D, red=False):
    """jeTrancy's knob, 128 frames of D x D (knob_page0.png white cap, knob_page1.png red cap: 210 px frames, 16 x 8)."""
    src = Image.open(os.path.join(JT, "knob_page1.png" if red else "knob_page0.png")).convert("RGBA")
    strip = Image.new("RGBA", (D, D * 128), (0, 0, 0, 0))
    for i in range(128):
        c, r = i % 16, i // 16
        strip.paste(src.crop((c * 210, r * 210, c * 210 + 210, r * 210 + 210)).resize((D, D), Image.LANCZOS), (0, i * D))
    return strip


def knob_scale(d, cx, cy, R, bipolar=False, col=INK_DIM):
    """Printed scale round a knob: 11 ticks over 270 degrees, longer at the ends (and the centre when bipolar), +/- marks."""
    for i in range(11):
        a = math.radians(135 + i * 27)
        L = 7 if i in (0, 10) or (bipolar and i == 5) else 4
        d.line([cx + R * math.cos(a), cy + R * math.sin(a), cx + (R + L) * math.cos(a), cy + (R + L) * math.sin(a)], fill=col, width=2)
    if bipolar:
        f = font(13)
        d.text((cx - R * 1.05, cy + R * 1.05), "-", font=f, fill=col, anchor="mm")
        d.text((cx + R * 1.05, cy + R * 1.05), "+", font=f, fill=col, anchor="mm")


# ---- fader (a long JP fader: slot with ticks, jeTrancy's cap) ---------------------------------------------------------
_CAP = {}


def fader_cap(w, red=False):
    k = (w, red)
    if k not in _CAP:
        c = Image.open(os.path.join(JT, "slider2.png" if red else "slider.png")).convert("RGBA")
        _CAP[k] = c.resize((w, int(c.height * w / c.width)), Image.LANCZOS)
    return _CAP[k]


def fader_frame(w, h, value, red=False):
    """One frame of a vertical fader film strip: transparent (the printed slot shows), the cap at the value (0 = bottom)."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cap = fader_cap(w, red)
    travel = h - cap.height
    y = int(round((1 - value) * travel))
    img.alpha_composite(cap, (0, y))
    return img


def fader_slot(img, cx, y0, y1, ticks=11, bipolar=False):
    """Printed fader slot: a black groove with a dark rim and tick marks either side (white, the centre longer if bipolar)."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([cx - 4, y0, cx + 4, y1], 3, fill=(0, 0, 0), outline=(44, 48, 60))
    for i in range(ticks):
        y = y0 + 6 + i * (y1 - y0 - 12) / (ticks - 1)
        L = 12 if i in (0, ticks - 1) or (bipolar and i == ticks // 2) else 8
        d.line([cx - 14 - L, y, cx - 14, y], fill=INK_DIM, width=2)
        d.line([cx + 14, y, cx + 14 + L, y], fill=INK_DIM, width=2)


def film_strip(frames):
    w, h = frames[0].size
    strip = Image.new("RGBA", (w, h * len(frames)), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.paste(f, (0, i * h))
    return strip


# ---- rubber keys with LEDs (drawn after jeTrancy's button_black_led / button_red_led) -----------------------------------
def key(w, h, lit=False, caption=None, led=True, red=False, size=None):
    """A JP rubber key: a black (or dark red) cap with a soft top light and a cast shadow, an LED slot at the top centre (lit:
    bright red with a glow), the caption in white below it. Same 6 px padding as the JV keys (bounds = key + 12)."""
    pad = 6
    W, H = (w + 2 * pad) * SS, (h + 2 * pad) * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle([pad * SS, (pad + 2) * SS, (pad + w) * SS, (pad + h + 3) * SS], 5 * SS, fill=220)
    img.paste((0, 0, 0, 255), (0, 0), sh.filter(ImageFilter.GaussianBlur(3 * SS)))
    out = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    od = ImageDraw.Draw(out)
    top, bot = ((92, 52, 56), (54, 28, 32)) if red else ((62, 62, 66), (22, 22, 24))
    od.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], 5 * SS, fill=(6, 6, 7, 255))
    for yy in range(SS, h * SS - SS):
        t = yy / (h * SS)
        od.line([SS, yy, w * SS - SS - 1, yy], fill=lerp(top, bot, min(1, t * 1.3)) + (255,))
    od.line([4 * SS, SS + 1, w * SS - 5 * SS, SS + 1], fill=tuple(min(255, v + 60) for v in top) + (255,), width=SS)
    small = h < 34
    if led or lit:
        lw, lh = (4 * SS, h * SS - 14 * SS) if small else (min(28, w // 3) * SS, 4 * SS)
        lx, ly = (8 * SS, 7 * SS) if small else ((w * SS - lw) // 2, 6 * SS)
        if lit:
            glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
            ImageDraw.Draw(glow).rounded_rectangle([lx - 5 * SS, ly - 4 * SS, lx + lw + 5 * SS, ly + lh + 4 * SS], 3 * SS, fill=LED_ON + (190,))
            out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3 * SS)))
            od = ImageDraw.Draw(out)
        od.rounded_rectangle([lx, ly, lx + lw, ly + lh], SS, fill=(LED_ON if lit else (60, 10, 10)) + (255,), outline=(14, 2, 2, 255))
        if lit:
            od.line([lx + SS, ly + SS, lx + lw - SS, ly + SS], fill=(255, 200, 180, 255), width=SS)
    if caption:
        s = size or min(15, h * 0.36)
        cy = (h * SS) // 2 + (5 * SS if (led or lit) and not small else 0)
        cx = (w * SS) // 2 + (5 * SS if (led or lit) and small else 0)
        od.text((cx, cy), caption, font=font(s * SS), fill=INK + (255,), anchor="mm")
    img.alpha_composite(out, (pad * SS, pad * SS))
    return img.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS)


# ---- the green LCD ----------------------------------------------------------------------------------------------------
def lcd_screen(img, x0, y0, x1, y1, cells=True):
    """A green-on-black LCD in a black bezel: dark green glass, a faint dot-cell texture (unlit pixels), a top shadow and a
    thin glass reflection. Live text goes on top as Labels in LCD_INK."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10], 6, fill=(2, 2, 3), outline=(52, 58, 74), width=2)
    for y in range(y0, y1 + 1):
        t = abs((y - y0) / max(1, y1 - y0) - 0.4)
        d.line([x0, y, x1, y], fill=lerp(LCD_GLASS, LCD_BG, min(1, t * 1.6)))
    if cells:
        for y in range(y0 + 3, y1 - 2, 4):
            for x in range(x0 + 3, x1 - 2, 4):
                d.point((x, y), fill=(14, 36, 18))
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).rectangle([x0, y0, x1, y0 + 6], fill=140)
    sh = sh.filter(ImageFilter.GaussianBlur(4))
    clip = Image.new("L", img.size, 0)
    ImageDraw.Draw(clip).rectangle([x0, y0, x1, y1], fill=255)
    img.paste((0, 0, 0), (0, 0), ImageChops.multiply(sh, clip))
    gl = Image.new("L", img.size, 0)
    ImageDraw.Draw(gl).polygon([(x0, y0), (x0 + (x1 - x0) * 0.35, y0), (x0 + (x1 - x0) * 0.2, y1), (x0, y1)], fill=10)
    img.paste((255, 255, 255), (0, 0), ImageChops.multiply(gl, clip))


def lcd_rule(d, x0, x1, y):
    for x in range(x0, x1, 4):
        d.line([x, y, x + 1, y], fill=LCD_DIM)


def lcd_vrule(d, x, y0, y1):
    for y in range(y0, y1, 4):
        d.line([x, y, x, y + 1], fill=LCD_DIM)


def lcd_caption(d, x, y, text, size=13, anchor="la"):
    d.text((x, y), text, font=font(size), fill=(50, 170, 80), anchor=anchor)


def lcd_arrow(d, cx, cy, direction, col=LCD_INK):
    hw, hh = 7, 11
    pts = [(cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy)] if direction < 0 else [(cx - hw, cy - hh), (cx - hw, cy + hh), (cx + hw, cy)]
    d.polygon(pts, fill=col)


def lcd_key(w, h, lit, caption, size=None):
    """An on-screen LCD choice: green outline and text; selected = inverse video (black text on a green bar)."""
    pad = 6
    W, H = (w + 2 * pad) * SS, (h + 2 * pad) * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = pad * SS, pad * SS, (pad + w) * SS - 1, (pad + h) * SS - 1
    if lit:
        d.rectangle([x0, y0, x1, y1], fill=LCD_INK + (255,))
    else:
        d.rectangle([x0, y0, x1, y1], outline=(40, 140, 66, 255), width=2 * SS)
    if caption:
        s = size or min(15, h * 0.42)
        d.text(((x0 + x1) // 2, (y0 + y1) // 2), caption, font=font(s * SS), fill=((4, 14, 6) if lit else LCD_INK) + (255,), anchor="mm")
    return img.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS)


def lcd_tile(w, h, lit):
    """A list row on the LCD (bank / patch): transparent so the name Label shows; lit = a green frame with a marker."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if lit:
        d.rectangle([0, 0, w - 1, h - 1], fill=LCD_INK + (40,), outline=LCD_INK + (255,), width=2)
        d.polygon([(5, 6), (5, h - 7), (12, h // 2)], fill=LCD_INK + (255,))
    else:
        for x in range(4, w - 4, 4):
            d.point((x, h - 2), fill=LCD_DIM + (255,))
    return img
