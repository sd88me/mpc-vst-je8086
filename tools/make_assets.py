#!/usr/bin/env python3
"""Images cut from gearmulator's JE-8086 skin "jeTrancy" (skin/jeTrancy/, by theusualsuspects, GPL-3.0):
  skin/parts/bg.png           the blue chassis at the MPC's 1280 x 628 (the empty middle of background.png)
  skin/parts/wordmark.png     the orange "JE-8086 / ANALOG MODELING EMULATOR" logo with its own alpha
  vst/images/knob_je.png      the knob filmstrip (knob_page0.png: 128 frames of 210 px in a 16 x 8 grid -> 101 frames of 104 px)
  vst/images/tile.png         the 270 x 110 Instruments-browser tile
Committed outputs, so a build does not need the large sources."""
import os
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SK = os.path.join(ROOT, "skin", "jeTrancy")
PARTS = os.path.join(ROOT, "skin", "parts")
IMG = os.path.join(ROOT, "vst", "images")
os.makedirs(PARTS, exist_ok=True)
os.makedirs(IMG, exist_ok=True)
W, H = 1280, 628

bg = Image.open(os.path.join(SK, "background.png")).convert("RGB")
chassis = bg.crop((200, 260, 2560, 1330)).resize((W, H), Image.LANCZOS)
chassis.save(os.path.join(PARTS, "bg.png"))

# wordmark: orange and white on a flat blue; alpha from the distance to the local blue
x0, y0, x1, y1 = 160, 40, 700, 175
wm = bg.crop((x0, y0, x1, y1))
ref = bg.getpixel((x1 + 30, (y0 + y1) // 2))
out = Image.new("RGBA", wm.size)
wp, op = wm.load(), out.load()
for y in range(wm.height):
    for x in range(wm.width):
        p = wp[x, y]
        d = max(abs(p[c] - ref[c]) for c in range(3))
        a = max(0, min(255, int((d - 18) * 4)))
        if a == 0:
            op[x, y] = (0, 0, 0, 0)
            continue
        al = a / 255.0
        op[x, y] = tuple(max(0, min(255, int((p[c] - ref[c] * (1 - al)) / al))) for c in range(3)) + (a,)
out = out.crop(out.getbbox())
out.save(os.path.join(PARTS, "wordmark.png"))

src = Image.open(os.path.join(SK, "knob_page0.png")).convert("RGBA")
fw = src.width // 16
film = Image.new("RGBA", (104, 104 * 101))
for i in range(101):
    f = i * 127 // 100
    x0, y0 = (f % 16) * fw, (f // 16) * fw
    fr = src.crop((x0 + 38, y0 + 38, x0 + 172, y0 + 172))      # the knob without most of the frame's empty margin, so it fills its box
    film.paste(fr.resize((104, 104), Image.LANCZOS), (0, i * 104))
film.save(os.path.join(IMG, "knob_je.png"))

tile = chassis.resize((270, 110), Image.LANCZOS)
s = min(240 / out.width, 90 / out.height)
l = out.resize((int(out.width * s), int(out.height * s)), Image.LANCZOS)
tile.paste(l, ((270 - l.width) // 2, (110 - l.height) // 2), l)
tile.save(os.path.join(IMG, "tile.png"))
print("assets written")
