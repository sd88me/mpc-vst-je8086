#!/usr/bin/env python3
"""The JE-8086 2.0 skin pages. Each page's coordinates are defined once, here: a Page draws its static art (chassis, black section
panels, print, knob scales, fader slots, the LCD) into a background PNG and records the live widgets (knob and fader film strips,
value labels, LED keys, LCD fields, list tiles) for TUI.json at exactly the same positions. Structure from JV-880 2.0's skin_pages.py.

Tabs: MAIN, BANKS, OSC, FILTER / AMP, ENVELOPES, EFFECTS, PERFORM, CONTROL (3 sub-tabs), VELOCITY (3 sub-tabs).
MAIN has one combined LCD (bank and patch, key mode, panel, voices, tempo, arpeggio, status) instead of several small displays;
the other tabs share a slim LCD with the bank and patch. Sections follow the JP-8080 panel; each Q-Link group of up to four
controls has its own black section (the MPC's bounds overlay frames it). Content area: 1280 x 628 (110 px down the screen).
"""
import os, re
from PIL import Image, ImageDraw

import make_je_skin as art
import make_tui as tui

SKINS = tui.OUT
_made = set()
KD = 66                    # knob diameter
LCD_TXT = "ff46ff6e"       # live LCD text
WHITE = "ffececec"


def asset(name, make):
    if name not in _made:
        make().save(os.path.join(SKINS, name))
        _made.add(name)
    return name


_SRC = None


def spec(key):
    """(min, max, options) of a parameter, from the generated table."""
    global _SRC
    if _SRC is None:
        _SRC = open(os.path.join(tui.ROOT, "src", "params_gen.h")).read()
    m = re.search(r'\{"%s", "[^"]*", (-?[\d.]+)f, (-?[\d.]+)f, (-?[\d.]+)f, (\d+), (ch_\d+|nullptr)' % re.escape(key), _SRC)
    if not m:
        raise SystemExit("skin: no parameter %s" % key)
    lo, hi = float(m.group(1)), float(m.group(2))
    opts = None
    if m.group(5) != "nullptr":
        opts = re.findall(r'"([^"]*)"', re.search(r"%s\[\] = \{(.*?)\};" % m.group(5), _SRC).group(1))
    return lo, hi, opts


def slug(s):
    return re.sub(r"[^A-Za-z0-9]", "_", (s or "blank").replace("+", "p").replace("-", "m").replace("#", "n").replace("/", "_"))


class Page:
    def __init__(self, name, key_name, fn, sub=0):
        self.name, self.key_name, self.fn, self.sub = name, key_name, fn, sub
        self.bg = art.chassis()
        self.d = ImageDraw.Draw(self.bg)
        self.kids, self.groups, self.qlink_rows, self.choices = [], [], [], {}
        self.sample, self.env_samples = {}, {}
        self.lcds = []
        self.overlay = []          # shown over everything while kb_open = 1 (the +FAV naming keyboard)

    def inside(self, x, y):
        return any(r[0] - 2 <= x <= r[2] + 2 and r[1] - 2 <= y <= r[3] + 2 for r in self.lcds)

    def lcd(self, x0, y0, x1, y1):
        art.lcd_screen(self.bg, x0, y0, x1, y1)
        self.lcds.append((x0, y0, x1, y1))

    # ---- static art ----
    def section(self, x0, y0, x1, y1, title=None, q=False):
        art.section(self.bg, x0, y0, x1, y1, title, q)

    def legend(self, x, y, text, size=15, col=art.INK, anchor="ma"):
        art.legend(self.d, x, y, text, size, col, anchor)

    # ---- widgets ----
    def value(self, key, x, y, w, h=24, just="horizontallyCentred verticallyCentred", colour=WHITE, size=19.0, sample=None, style="Medium", case="Upper Case"):
        self.kids.append(tui.label("Value", "%d %d %d %d" % (x, y, w, h), remap=tui.P(key), just=just, colour=colour, style=style, h=size, case=case))
        if sample is not None:
            self.sample[key + "$"] = sample

    def knob(self, key, cx, cy, name, sample=0.5, red=False, D=KD, show_value=True):
        """A knob centred at (cx, cy): its name above, the printed scale round it, the value below (drag up / down, Q-Link on
        touch, the big overlay on a double tap)."""
        lo, hi, opts = spec(key)
        bip = lo < 0 < hi
        if opts:
            self.choices[key] = opts
        if name:
            self.legend(cx, cy - D // 2 - 30, name, 14)
        art.knob_scale(self.d, cx, cy, D * 0.5 + 3, bip)
        comp = "knob%d%s" % (D, "r" if red else "")
        tui.need_slider(comp, asset("knob_%d%s.png" % (D, "r" if red else ""), lambda: art.knob_strip(D, red)), D, D, "Vertical")
        self.kids.append(tui.entry(key, comp, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (cx - D // 2, cy - D // 2, D, D),
                                   remap=tui.P(key), focus="Yes"))
        if show_value:
            self.value(key, cx - 60, cy + D // 2 + 8, 120, 22, size=17.0, colour="ffb4bccc")
        self.sample[key] = sample
        self.sample[key + "$"] = str(int(round(lo + sample * (hi - lo))))

    def fader(self, key, cx, y0, y1, name, sample=0.5, red=False):
        """A long vertical fader: the printed slot from y0 to y1, its name above, the value under it."""
        lo, hi, _ = spec(key)
        bip = lo < 0 < hi
        art.fader_slot(self.bg, cx, y0, y1, bipolar=bip)
        if name:
            self.legend(cx, y0 - 30, name, 15)
        cw = 40
        ch = art.fader_cap(cw, red).height
        h = y1 - y0 + ch
        comp = "fader%dx%d%s" % (cw, h, "r" if red else "")
        tui.need_slider(comp, asset("fader_%dx%d%s.png" % (cw, h, "r" if red else ""), lambda: art.film_strip(
            [art.fader_frame(cw, h, i / 127, red) for i in range(128)])), cw, h, "Vertical")
        self.kids.append(tui.entry(key, comp, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (cx - cw // 2, y0 - ch // 2, cw, h),
                                   remap=tui.P(key), focus="Yes"))
        self.value(key, cx - 50, y1 + ch // 2 + 4, 100, 22, size=17.0, colour="ffb4bccc")
        self.sample[key] = sample
        self.sample[key + "$"] = str(int(round(lo + sample * (hi - lo))))

    def keyimg(self, x, y, w, h, lit, caption, led=True, size=None, red=False):
        if self.inside(x + 2, y + 2):
            return asset("lcdkey_%dx%d_%s_%s.png" % (w, h, "on" if lit else "off", slug(caption)), lambda: art.lcd_key(w, h, lit, caption, size))
        return asset("key_%dx%d_%s_%s%s%s.png" % (w, h, "on" if lit else "off", slug(caption), "" if led else "_nl", "_r" if red else ""),
                     lambda: art.key(w, h, lit, caption, led=led, red=red, size=size))

    def toggle(self, key, x, y, w, h, caption, lit=False, red=False):
        on, off = self.keyimg(x, y, w, h, True, caption, red=red), self.keyimg(x, y, w, h, False, caption, red=red)
        self.kids.append(tui.button(key, key, on, off, "%d %d %d %d" % (x - 6, y - 6, w + 12, h + 12)))
        _, _, opts = spec(key)
        if opts:
            self.choices[key] = opts
        self.sample[key + "#"] = 1 if lit else 0

    def momentary(self, key, x, y, w, h, caption, size=None, red=False):
        on, off = self.keyimg(x, y, w, h, True, caption, False, size, red), self.keyimg(x, y, w, h, False, caption, False, size, red)
        self.kids.append(tui.button(key, key, on, off, "%d %d %d %d" % (x - 6, y - 6, w + 12, h + 12)))

    def segments(self, key, x, y, w, h, labels=None, cols=None, gap=6, sel=0, row_gap=8, size=None):
        """A radio group of LED keys, one per option (captions baked), in `cols` columns; returns the bottom y."""
        opts = spec(key)[2]
        labels = labels or opts
        cols = cols or len(labels)
        rows = (len(labels) + cols - 1) // cols
        bw = (w - (cols - 1) * gap) // cols
        for i, lb in enumerate(labels):
            r, c = divmod(i, cols)
            bx, by = x + c * (bw + gap), y + r * (h + row_gap)
            on, off = self.keyimg(bx, by, bw, h, True, lb, size=size), self.keyimg(bx, by, bw, h, False, lb, size=size)
            self.kids.append(tui.button("%s %d" % (key, i), key, on, off, "%d %d %d %d" % (bx - 6, by - 6, bw + 12, h + 12),
                                        button_id=i, group=len(labels)))
        self.choices[key] = opts or labels
        self.sample[key + "#"] = sel
        return y + rows * h + (rows - 1) * row_gap

    def lcd_field(self, key, x, y, w, h):
        self.kids.append(tui.entry(key + " field", "lcdfield%dx%d" % (w, h), {"version": 1, "handleName": "Data"},
                                   "%d %d %d %d" % (x, y, w, h), remap=tui.P(key), focus="Yes"))
        tui.need_field(w, h)

    def lcd_param(self, key, x, y, w, h, caption, sample, size=24.0):
        """A field of the LCD: a small green caption over the live value (an option's name or the number); drag, the data wheel
        or a Q-Link sets it."""
        art.lcd_caption(self.d, x + 8, y + 4, caption)
        self.value(key, x + 6, y + 20, w - 12, h - 24, just="left verticallyCentred", colour=LCD_TXT, size=size, sample=sample, style="Bold")
        self.lcd_field(key, x, y, w, h)
        _, _, opts = spec(key)
        if opts:
            self.choices[key] = opts

    def hit(self, key, x, y, w, h):
        """An invisible momentary touch zone (on printed LCD arrows)."""
        off = asset("hit_off_%dx%d.png" % (w, h), lambda: Image.new("RGBA", (w, h), (0, 0, 0, 0)))
        on = asset("hit_on_%dx%d.png" % (w, h), lambda: Image.new("RGBA", (w, h), (70, 255, 110, 60)))
        self.kids.append(tui.button(key, key, on, off, "%d %d %d %d" % (x, y, w, h), focus="No"))

    def qlink_group(self, rect, keys):
        x0, y0, x1, y1 = rect
        self.groups.append("%d %d %d %d" % (x0, y0, x1 - x0, y1 - y0))
        self.qlink_rows.append(keys)

    def tab(self):
        self.bgname = "bg_%s.png" % re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")
        self.bg.save(os.path.join(SKINS, self.bgname))
        kids = [tui.entry("bg", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": self.bgname}, "0 0 1280 628")] + self.kids + self.overlay
        return {"version": 1, "tabName": self.key_name, "fnKeyIndex": self.fn, "fnKeySubIndex": self.sub,
                "componentDefinition": tui.component(kids, background=tui.bg("ff1a2030")), "qlinkBoundsData": self.groups}


# ---- shared parts ------------------------------------------------------------------------------------------------------
def fav_keys(p, x, y):
    """+FAV / -FAV (favourites in the MPC's PRESET menu) and the count, on every page."""
    p.value("fav_text", x - 6, y - 26, 220, 20, colour="ffff6a14", size=14.0, style="SemiBold", sample="FAVOURITES 3 / 64")
    p.momentary("fav_save", x, y, 96, 44, "+ FAV", size=16)
    p.momentary("fav_delete", x + 112, y, 96, 44, "- FAV", size=16)
    keyboard(p)


KB_ROWS = [("1234567890", ["kb_bksp"]), ("QWERTYUIOP", []), ("ASDFGHJKL-", []), ("ZXCVBNM", ["kb_space"])]


def keyboard(p):
    """The naming keyboard for +FAV (Vavra's / Profit-5's): a full-page panel, the name being typed in an LCD, 42 rubber keys;
    shown while kb_open = 1, over everything else on the page (added last)."""
    ind = ["IndexedEnabling/1/2/%s" % tui.P("kb_open")]
    def make_panel():
        img = art.chassis().convert("RGBA")
        art.section(img, 16, 8, 1264, 620)
        d = ImageDraw.Draw(img)
        art.legend(d, 40, 34, "FAVOURITE NAME", 20, art.ORANGE, anchor="lm")
        art.lcd_screen(img, 300, 14, 1240, 82)
        return img.convert("RGB")
    p.overlay.append(tui.entry("kb panel", "Image", {"version": 2, "imageType": "Regular", "colour": "0",
                                                     "image": asset("kb_panel.png", make_panel)}, "0 0 1280 628", ind=ind))
    lab = tui.label("Value", "320 22 900 52", remap=tui.P("fav_name"), just="left verticallyCentred", colour=LCD_TXT, style="Bold",
                    h=40.0, case="Original")
    lab["bounds"] = tui.bounds("320 22 900 52", ind=ind)
    p.overlay.append(lab)
    p.sample["fav_name$"] = "Trancer Lead_"
    kw, kh, gap, x0, y0 = 98, 84, 8, 64, 104

    def kbkey(k, cap, x, y, w, red=False):
        on = asset("kb_%dx%d_on_%s%s.png" % (w, kh, slug(cap), "_r" if red else ""), lambda: art.key(w, kh, True, cap, led=False, red=red, size=26 if len(cap) == 1 else 19))
        off = asset("kb_%dx%d_off_%s%s.png" % (w, kh, slug(cap), "_r" if red else ""), lambda: art.key(w, kh, False, cap, led=False, red=red, size=26 if len(cap) == 1 else 19))
        p.overlay.append(tui.button(k, k, on, off, "%d %d %d %d" % (x - 6, y - 6, w + 12, kh + 12), focus="No", ind=ind))
    for r, (chars, extra) in enumerate(KB_ROWS):
        y = y0 + r * (kh + gap)
        x = x0 + r * 30
        for c in chars:
            kbkey("kb_" + ("dash" if c == "-" else c.lower()), c, x, y, kw)
            x += kw + gap
        for k in extra:
            kbkey(k, {"kb_bksp": "DELETE", "kb_space": "SPACE"}[k], x, y, 1216 - x)
    y = y0 + 4 * (kh + gap)
    kbkey("kb_shift", "SHIFT", x0, y, 220)
    kbkey("kb_cancel", "CANCEL", 640 - 130, y, 260)
    kbkey("kb_save", "SAVE", 1216 - 260, y, 260, red=True)


def bank_patch_row(p, x0, x1, y0, y1, big=34.0, split=0.36):
    """The LCD's first line: < BANK > | < PATCH NAME >, the arrows are touch zones, each name also takes the data wheel."""
    d = p.d
    sx = int(x0 + (x1 - x0) * split)
    cy = (y0 + y1) // 2
    for ax, dr in ((x0 + 22, -1), (sx - 22, 1), (sx + 22, -1), (x1 - 22, 1)):
        art.lcd_arrow(d, ax, cy, dr)
    art.lcd_vrule(d, sx, y0 + 6, y1 - 6)
    p.value("bank_name", x0 + 44, y0, sx - x0 - 88, y1 - y0, just="left verticallyCentred", colour=LCD_TXT, size=big * 0.78, style="Bold",
            case="Original", sample="PATCH A")
    p.value("preset_name", sx + 44, y0, x1 - sx - 88, y1 - y0, just="left verticallyCentred", colour=LCD_TXT, size=big, style="Bold",
            case="Original", sample="001 Spit'n Slide Bs")
    p.lcd_field("bank_index", x0 + 44, y0, sx - x0 - 88, y1 - y0)
    p.lcd_field("preset", sx + 44, y0, x1 - sx - 88, y1 - y0)
    for key, x in (("bank_prev", x0), ("bank_next", sx - 44), ("preset_prev", sx), ("preset_next", x1 - 44)):
        p.hit(key, x, y0, 44, y1 - y0)


def header(p):
    """Every page but MAIN: the wordmark, the slim LCD with bank and patch, +FAV / -FAV."""
    w = art.wordmark(54)
    p.bg.paste(w, (14, 14), w)
    p.lcd(262, 16, 1010, 70)
    bank_patch_row(p, 262, 1010, 16, 70, big=30.0)
    fav_keys(p, 1048, 28)


def knob_row(p, x0, x1, cy, ctl, red=(), D=KD):
    """Knobs evenly over [x0, x1] at height cy. ctl: [(key, name, sample)]."""
    n = len(ctl)
    step = (x1 - x0) / n
    for i, (k, nm, s) in enumerate(ctl):
        p.knob(k, int(x0 + step * (i + 0.5)), cy, nm, s, red=k in red, D=D)


def knob_block(p, x0, y0, x1, y1, title, ctl, extra_q=(), red=()):
    """A section of up to four knobs in a row = one Q-Link group."""
    p.section(x0, y0, x1, y1, title, q=True)
    knob_row(p, x0 + 6, x1 - 6, y0 + 92, ctl, red)
    p.qlink_group((x0, y0, x1, y1), [c[0] for c in ctl] + list(extra_q))


# ---------------------------------------------------------------------------------------------------------------------------
def main_page():
    """MAIN: one combined LCD (bank | patch on top; KEY MODE, PANEL, VOICES, TEMPO, ARP fields; status line), the quick-edit
    knobs and the amp envelope faders as four Q-Link blocks, the play-mode keys on the right."""
    p = Page("MAIN", "MAIN", 0)
    w = art.wordmark(62)
    p.bg.paste(w, (14, 18), w)
    # the combined LCD
    X0, Y0, X1, Y1 = 290, 16, 1010, 222
    p.lcd(X0, Y0, X1, Y1)
    bank_patch_row(p, X0, X1, Y0, Y0 + 66, big=34.0)
    art.lcd_rule(p.d, X0 + 8, X1 - 8, Y0 + 70)
    fields = [("key_mode", "KEY MODE", "SINGLE"), ("edit_part", "PANEL", "UPPER"), ("voice_assign", "VOICES", "8-2"),
              ("tempo", "TEMPO", "120"), ("arp_mode", "ARPEGGIO", "UP")]
    fw = (X1 - X0) // len(fields)
    for i, (k, cap, smp) in enumerate(fields):
        fx = X0 + i * fw
        if i:
            art.lcd_vrule(p.d, fx, Y0 + 80, Y0 + 140)
        p.lcd_param(k, fx + 4, Y0 + 74, fw - 8, 70, cap, smp)
    art.lcd_rule(p.d, X0 + 8, X1 - 8, Y0 + 148)
    p.value("loading_status", X0 + 14, Y0 + 154, 330, 46, just="left verticallyCentred", colour=LCD_TXT, size=18.0, style="Medium",
            case="Original", sample="Ready - ROM loaded")
    p.value("engine_stats", X0 + 360, Y0 + 154, X1 - X0 - 374, 46, just="right verticallyCentred", colour=LCD_TXT, size=18.0,
            style="Medium", case="Original", sample="DROPOUTS 0   CPU 50%")
    # right of the LCD: favourites, PANIC, reload
    fav_keys(p, 1048, 40)
    p.momentary("all_notes_off", 1048, 112, 96, 44, "PANIC", size=15, red=True)
    p.momentary("init_patch", 1160, 112, 96, 44, "RELOAD", size=15)
    p.legend(1110, 182, "GAIN %", 13, art.INK_DIM)
    p.value("gain", 1150, 174, 100, 24, just="left verticallyCentred", colour="ffb4bccc", size=17.0, sample="100")
    # quick edit: filter and oscillator knobs, amp envelope faders, effects
    knob_block(p, 16, 240, 512, 420, "FILTER", [("cutoff", "CUTOFF", .6), ("resonance", "RESONANCE", .2),
                                                ("filter_env_depth", "ENV DEPTH", .7), ("key_follow", "KEY FOLLOW", .5)], red=("cutoff",))
    knob_block(p, 524, 240, 1020, 420, "OSC", [("osc1_ctrl1", "OSC1 CTRL 1", .4), ("osc1_ctrl2", "OSC1 CTRL 2", .5),
                                               ("osc_balance", "BALANCE", .5), ("lfo1_rate", "LFO1 RATE", .6)])
    p.section(16, 432, 512, 620, "AMP ENVELOPE", q=True)
    for i, (k, nm, s) in enumerate([("amp_attack", "A", .05), ("amp_decay", "D", .5), ("amp_sustain", "S", .8), ("amp_release", "R", .3)]):
        p.fader(k, 84 + i * 112, 492, 580, nm, s)
    p.qlink_group((16, 432, 512, 620), ["amp_attack", "amp_decay", "amp_sustain", "amp_release"])
    knob_block(p, 524, 432, 1020, 620, "EFFECTS", [("chorus_level", "CHORUS", .3), ("delay_time", "DELAY TIME", .5),
                                                   ("delay_feedback", "FEEDBACK", .3), ("delay_level", "DELAY LEVEL", .3)])
    # play-mode keys (the panel's KEY MODE / PANEL SELECT / ARPEGGIATOR)
    RX, RW = 1036, 228
    p.section(RX - 4, 240, RX + RW + 4, 620)
    p.legend(RX + RW // 2, 250, "KEY MODE", 14, art.ORANGE)
    yb = p.segments("key_mode", RX + 8, 276, RW - 16, 40, gap=8, size=13)
    p.legend(RX + RW // 2, yb + 14, "PANEL", 14, art.ORANGE)
    yb = p.segments("edit_part", RX + 8, yb + 40, RW - 16, 40, gap=8, size=13)
    p.legend(RX + RW // 2, yb + 14, "ARPEGGIATOR", 14, art.ORANGE)
    p.toggle("arp_switch", RX + 8, yb + 40, (RW - 24) // 2, 44, "ON")
    p.toggle("arp_hold", RX + 16 + (RW - 24) // 2, yb + 40, (RW - 24) // 2, 44, "HOLD")
    p.legend(RX + RW // 2, yb + 104, "VELOCITY", 14, art.ORANGE)
    p.toggle("velocity_switch", RX + 8, yb + 130, RW - 16, 40, "VELOCITY")
    return p


def banks_page():
    """BANKS: the 8 banks and the browsed bank's 32 entries (paged) as LCD lists."""
    p = Page("BANKS", "BANKS", 1)
    header(p)
    p.lcd(20, 104, 300, 560)
    p.lcd(324, 104, 1260, 560)
    art.lcd_caption(p.d, 30, 108, "BANK")
    names = ["PATCH A", "PATCH B", "PERFORMANCES", "MY BANK"]
    for i in range(8):
        y = 128 + i * 52
        k = "bank_slot_%d" % (i + 1)
        p.value(k, 44, y, 240, 46, just="left verticallyCentred", colour=LCD_TXT, size=20.0, style="Medium", case="Original",
                sample=names[i] if i < len(names) else "")
        p.kids.append(tui.button(k, k, asset("lcdtile_270x46_on.png", lambda: art.lcd_tile(270, 46, True)),
                                 asset("lcdtile_270x46_off.png", lambda: art.lcd_tile(270, 46, False)), "25 %d 270 46" % y))
        p.sample[k + "#"] = 1 if i == 0 else 0
    art.lcd_caption(p.d, 334, 108, "PATCH")
    pn = ["Spit'n Slide Bs", "Velo Decay Bass", "Trance Saw", "Hoover", "Super Strings", "Juno Pad", "Acid Line", "Sync Lead"]
    for i in range(32):
        c, r = divmod(i, 8)
        x, y = 330 + c * 232, 128 + r * 52
        k = "patch_slot_%d" % (i + 1)
        p.value(k, x + 18, y, 206, 46, just="left verticallyCentred", colour=LCD_TXT, size=17.0, style="Medium", case="Original",
                sample="%03d %s" % (i + 1, pn[i % len(pn)]))
        p.kids.append(tui.button(k, k, asset("lcdtile_226x46_on.png", lambda: art.lcd_tile(226, 46, True)),
                                 asset("lcdtile_226x46_off.png", lambda: art.lcd_tile(226, 46, False)), "%d %d 226 46" % (x, y)))
        p.sample[k + "#"] = 1 if i == 0 else 0
    y = 576
    p.momentary("bank_page_prev", 24, y, 110, 40, "< BANKS", size=14)
    p.value("bank_page_text", 140, y, 40, 40, colour=WHITE, size=15.0, sample="1 / 1")
    p.momentary("bank_page_next", 186, y, 110, 40, "BANKS >", size=14)
    p.momentary("patch_page_prev", 330, y, 130, 40, "< PAGE", size=14)
    p.value("patch_page_text", 470, y, 300, 40, colour=WHITE, size=17.0, sample="PAGE 1 / 4")
    p.momentary("patch_page_next", 780, y, 130, 40, "PAGE >", size=14)
    p.momentary("random_patch", 1110, y - 4, 146, 48, "RANDOM", size=16, red=True)
    p.qlink_group((16, 92, 1268, 624), ["bank_index", "preset", "patch_page_prev", "patch_page_next"])
    return p


def osc_page():
    """OSC: LFO 1, OSC 1, OSC 2 and OSC COMMON, as on the panel's top-left (waveform keys with LEDs, knobs)."""
    p = Page("OSC", "OSC", 2)
    header(p)
    # LFO 1
    p.section(16, 92, 300, 356, "LFO 1", q=True)
    p.segments("lfo1_waveform", 30, 132, 256, 34, labels=["TRI", "SAW", "SQR", "S/H"], gap=6, size=13)
    knob_row(p, 22, 294, 262, [("lfo1_rate", "RATE", .6), ("lfo1_fade", "FADE", 0)])
    p.qlink_group((16, 92, 300, 356), ["lfo1_rate", "lfo1_fade", "lfo1_waveform"])
    # OSC 1
    p.section(312, 92, 760, 356, "OSC 1", q=True)
    p.segments("osc1_waveform", 328, 128, 190, 26, labels=["SUPER SAW", "TRIANGLE MOD", "NOISE", "FEEDBACK OSC", "SQUARE", "SAW", "TRIANGLE"],
               cols=1, gap=0, row_gap=6, size=12)
    knob_row(p, 520, 756, 252, [("osc1_ctrl1", "CTRL 1", .4), ("osc1_ctrl2", "CTRL 2", .5)])
    p.qlink_group((312, 92, 760, 356), ["osc1_ctrl1", "osc1_ctrl2", "osc1_waveform"])
    # OSC 2
    p.section(772, 92, 1264, 356, "OSC 2", q=True)
    p.segments("osc2_waveform", 788, 128, 120, 26, labels=["SQUARE", "SAW", "TRIANGLE", "NOISE"], cols=1, gap=0, row_gap=6, size=12)
    p.toggle("osc2_sync", 788, 270, 120, 34, "SYNC")
    knob_row(p, 912, 1260, 200, [("osc2_range", "RANGE", .5), ("osc2_fine", "FINE / WIDE", .5)], D=56)
    knob_row(p, 912, 1260, 300, [("osc2_ctrl1", "CTRL 1", .4), ("osc2_ctrl2", "CTRL 2", .5)], D=56)
    p.qlink_group((772, 92, 1264, 356), ["osc2_range", "osc2_fine", "osc2_ctrl1", "osc2_ctrl2"])
    # OSC COMMON
    p.section(16, 368, 1264, 620, "OSC COMMON", q=True)
    knob_row(p, 22, 820, 470, [("osc_balance", "OSC BALANCE", .5), ("cross_mod_depth", "X-MOD DEPTH", 0),
                               ("osc_lfo1_depth", "LFO1 DEPTH", .5), ("osc_shift", "OSC SHIFT", .5)])
    p.legend(1030, 400, "RING", 14, art.ORANGE)
    p.toggle("ring_mod", 960, 424, 140, 40, "RING MOD")
    p.legend(1030, 488, "LFO 1 & ENV DEST", 14, art.ORANGE)
    p.segments("lfo1_env_dest", 840, 514, 400, 40, labels=["OSC 1+2", "OSC 2", "X-MOD"], gap=8, size=13)
    p.qlink_group((16, 368, 1264, 620), ["osc_balance", "cross_mod_depth", "osc_lfo1_depth", "osc_shift"])
    return p


def filter_page():
    """FILTER / AMP: the filter (type, slope keys, cutoff, resonance, key follow, LFO 1 depth), the amp (level, LFO mode),
    MODULATION (LFO 2) and the tone control."""
    p = Page("FILTER / AMP", "FILTER", 3)
    header(p)
    p.section(16, 92, 760, 356, "FILTER", q=True)
    knob_row(p, 22, 590, 178, [("cutoff", "CUTOFF FREQ", .6), ("resonance", "RESONANCE", .2), ("key_follow", "KEY FOLLOW", .5)], red=("cutoff",), D=56)
    knob_row(p, 22, 590, 296, [("filter_lfo1_depth", "LFO1 DEPTH", .5), ("filter_lfo2_depth", "LFO2 DEPTH", .5), ("filter_env_depth", "ENV DEPTH", .7)], D=56)
    p.segments("filter_type", 610, 132, 136, 34, labels=["HPF", "BPF", "LPF"], cols=1, row_gap=8, sel=2, size=13)
    p.segments("cutoff_slope", 610, 272, 136, 34, labels=["-12 dB", "-24 dB"], cols=1, row_gap=8, sel=1, size=13)
    p.qlink_group((16, 92, 760, 356), ["cutoff", "resonance", "key_follow", "filter_env_depth"])
    p.section(772, 92, 1264, 356, "AMP", q=True)
    knob_row(p, 778, 1100, 178, [("amp_level", "LEVEL", .8), ("amp_lfo1_depth", "LFO1 / PAN", .5)], D=56)
    knob_row(p, 778, 1100, 296, [("amp_lfo2_depth", "LFO2 DEPTH", .5), ("gain", "GAIN %", .23)], D=56)
    p.legend(1180, 124, "LFO 1 MODE", 13, art.ORANGE)
    p.segments("amp_lfo1_mode", 1116, 148, 132, 34, labels=["OFF", "AUTO", "MANUAL"], cols=1, row_gap=8, size=13)
    p.qlink_group((772, 92, 1264, 356), ["amp_level", "amp_lfo1_depth", "amp_lfo2_depth", "gain"])
    p.section(16, 368, 760, 620, "MODULATION (LFO 2)", q=True)
    knob_row(p, 22, 560, 480, [("lfo2_rate", "RATE", .5), ("pitch_lfo2_depth", "PITCH DEPTH", .5), ("filter_lfo2_depth", "FILTER DEPTH", .5)])
    p.legend(660, 400, "DEPTH SELECT", 13, art.ORANGE)
    p.segments("lfo2_depth_select", 580, 424, 160, 34, labels=["PITCH", "FILTER", "AMP"], cols=1, row_gap=8, size=13)
    p.qlink_group((16, 368, 760, 620), ["lfo2_rate", "pitch_lfo2_depth", "filter_lfo2_depth", "lfo2_depth_select"])
    p.section(772, 368, 1264, 620, "TONE CONTROL", q=True)
    knob_row(p, 778, 1258, 480, [("tone_bass", "BASS", .5), ("tone_treble", "TREBLE", .5)])
    p.qlink_group((772, 368, 1264, 620), ["tone_bass", "tone_treble"])
    return p


def env_page():
    """ENVELOPES: the pitch, filter and amp envelopes as long faders, as on the panel's bottom row."""
    p = Page("ENVELOPES", "ENV", 4)
    header(p)
    Y0, Y1 = 196, 560
    blocks = [(16, 300, "PITCH ENV", [("pitch_env_depth", "DEPTH", .5), ("pitch_env_attack", "A", .1), ("pitch_env_decay", "D", .3)]),
              (312, 788, "FILTER ENV", [("filter_env_depth", "DEPTH", .7), ("filter_attack", "A", .05), ("filter_decay", "D", .45),
                                        ("filter_sustain", "S", .4), ("filter_release", "R", .3)]),
              (800, 1264, "AMP ENV", [("amp_attack", "A", .05), ("amp_decay", "D", .5), ("amp_sustain", "S", .8), ("amp_release", "R", .3)])]
    for x0, x1, title, ctl in blocks:
        p.section(x0, 92, x1, 620, title, q=True)
        n = len(ctl)
        step = (x1 - x0 - 20) / n
        xs = [int(x0 + 10 + step * (i + 0.5)) for i in range(n)]
        adsr = [i for i, c in enumerate(ctl) if c[1] in "ADSR" and len(c[1]) == 1]
        if adsr:
            art.bracket(p.d, xs[adsr[0]] - 30, xs[adsr[-1]] + 30, 146, "ENVELOPE")
        for i, (k, nm, s) in enumerate(ctl):
            p.fader(k, xs[i], Y0, Y1, nm, s, red=nm == "DEPTH")
        keys = [c[0] for c in ctl]
        p.qlink_group((x0, 92, x1, 620), keys[-4:] if len(keys) > 4 else keys)
    return p


def fx_page():
    """EFFECTS: chorus (type list on the LCD), delay, portamento, bend, solo / legato and morphing."""
    p = Page("EFFECTS", "EFFECTS", 5)
    header(p)
    p.section(16, 92, 630, 356, "CHORUS", q=True)
    p.lcd(36, 136, 400, 320)
    p.lcd_param("chorus_type", 36, 140, 364, 80, "TYPE", "SUPER CHORUS SLW", size=22.0)
    art.lcd_rule(p.d, 44, 392, 228)
    p.lcd_param("up_chorus_sync", 36, 234, 364, 80, "TEMPO SYNC (UPPER)", "OFF", size=22.0)
    knob_row(p, 400, 624, 250, [("chorus_level", "LEVEL", .3)])
    p.qlink_group((16, 92, 630, 356), ["chorus_type", "chorus_level", "up_chorus_sync"])
    p.section(642, 92, 1264, 356, "DELAY", q=True)
    p.lcd(662, 136, 900, 320)
    p.lcd_param("delay_type", 662, 140, 238, 80, "TYPE", "PANNING L->R", size=20.0)
    art.lcd_rule(p.d, 670, 892, 228)
    p.lcd_param("up_delay_sync", 662, 234, 238, 80, "TEMPO SYNC (UPPER)", "OFF", size=20.0)
    knob_row(p, 904, 1258, 250, [("delay_time", "TIME", .5), ("delay_feedback", "FEEDBACK", .3), ("delay_level", "LEVEL", .3)])
    p.qlink_group((642, 92, 1264, 356), ["delay_time", "delay_feedback", "delay_level", "delay_type"])
    p.section(16, 368, 630, 620, "PORTAMENTO / BEND", q=True)
    p.toggle("portamento", 40, 420, 120, 44, "PORTA")
    knob_row(p, 170, 624, 470, [("portamento_time", "PORTA TIME", .3), ("bend_up", "BEND UP", .1), ("bend_down", "BEND DOWN", .9)])
    p.qlink_group((16, 368, 630, 620), ["portamento_time", "bend_up", "bend_down", "portamento"])
    p.section(642, 368, 1264, 620, "CONTROL")
    art.bracket(p.d, 672, 930, 430, "SOLO SW")
    p.toggle("mono", 672, 450, 120, 44, "MONO")
    p.toggle("legato", 810, 450, 120, 44, "LEGATO")
    art.bracket(p.d, 960, 1234, 430, "MORPHING")
    p.toggle("morph_bend", 960, 450, 130, 44, "BEND MORPH")
    p.toggle("velocity_switch", 1104, 450, 130, 44, "VELOCITY")
    art.bracket(p.d, 672, 1234, 530, "ACTIVE")
    p.toggle("active_velocity", 672, 550, 170, 44, "VELOCITY")
    p.toggle("active_control", 868, 550, 170, 44, "CONTROL")
    p.toggle("active_bender", 1064, 550, 170, 44, "BENDER")
    return p


def perform_page():
    """PERFORM: key mode, split, part detune, voices, output; the arpeggiator; the upper and lower parts; individual trigger."""
    p = Page("PERFORM", "PERFORM", 6)
    header(p)
    p.section(16, 92, 630, 356, "KEY MODE", q=True)
    p.segments("key_mode", 36, 130, 576, 36, gap=10, size=14)
    p.segments("edit_part", 36, 178, 576, 36, labels=["UPPER", "LOWER", "UPPER & LOWER"], gap=10, size=14)
    knob_row(p, 22, 624, 284, [("split_point", "SPLIT POINT", .45), ("part_detune", "PART DETUNE", .5)], D=56)
    p.qlink_group((16, 92, 630, 356), ["split_point", "part_detune", "key_mode", "edit_part"])
    p.section(642, 92, 1264, 356, "VOICES / OUTPUT", q=True)
    p.lcd(662, 136, 950, 196)
    p.lcd_param("voice_assign", 662, 136, 288, 60, "VOICE ASSIGN (UPPER-LOWER)", "8-2", size=22.0)
    p.legend(1100, 128, "OUTPUT", 14, art.ORANGE)
    p.segments("output_assign", 972, 152, 270, 40, labels=["MIX", "PARALLEL"], gap=10, size=14)
    knob_row(p, 648, 1258, 284, [("up_transpose", "UPPER TRANSPOSE", .5), ("lo_transpose", "LOWER TRANSPOSE", .5)], D=56)
    p.qlink_group((642, 92, 1264, 356), ["voice_assign", "up_transpose", "lo_transpose", "output_assign"])
    p.section(16, 368, 1264, 620, "ARPEGGIATOR / RPS", q=True)
    p.toggle("arp_switch", 40, 420, 110, 44, "ON")
    p.toggle("arp_hold", 40, 486, 110, 44, "HOLD")
    p.lcd(180, 412, 1010, 476)
    lf = [("arp_mode", "MODE", "UP", 160), ("arp_beat", "BEAT", "1/16", 230), ("arp_range", "RANGE", "1 OCT", 140), ("arp_dest", "DEST", "LOWER & UPPER", 300)]
    x = 180
    for k, cap, smp, w in lf:
        p.lcd_param(k, x, 412, w, 64, cap, smp, size=20.0)
        x += w
        if x < 1000:
            art.lcd_vrule(p.d, x, 418, 470)
    knob_row(p, 1020, 1258, 470, [("tempo", "TEMPO", .45)], red=("tempo",))
    p.lcd(180, 516, 1010, 580)
    tf = [("trigger_dest", "TRIGGER DEST", "FILTER ENV", 260), ("trigger_ch", "TRIGGER CH", "10", 180), ("trigger_note", "TRIGGER NOTE", "ALL", 200),
          ("up_lfo1_sync", "LFO1 SYNC", "OFF", 190)]
    x = 180
    for k, cap, smp, w in tf:
        p.lcd_param(k, x, 516, w, 64, cap, smp, size=20.0)
        x += w
        if x < 1000:
            art.lcd_vrule(p.d, x, 522, 574)
    p.toggle("trigger_switch", 40, 552, 110, 44, "TRIGGER")
    p.qlink_group((16, 368, 1264, 620), ["arp_mode", "arp_beat", "arp_range", "tempo"])
    return p


ASSIGN = {
    "CONTROL": ("ctl_", ["lfo1_rate", "lfo1_fade", "lfo2_rate", "cross_modulation_depth", "oscillator_balance", "pitch_lfo1_depth",
                         "pitch_lfo2_depth", "pitch_envelope_depth", "pitch_envelope_attack_time", "pitch_envelope_decay_time", "osc1_control1",
                         "osc1_control2", "osc2_range", "osc2_fine_wide", "osc2_control1", "osc2_control2", "cutoff_frequency", "resonance",
                         "cutoff_freq_key_follow", "filter_lfo1_depth", "filter_lfo2_depth", "filter_env_depth", "filter_env_attack_time",
                         "filter_env_decay_time", "filter_env_sustain_level", "filter_env_release_time", "amp_level", "amp_lfo1_depth",
                         "amp_lfo2_depth", "amp_env_attack_time", "amp_env_decay_time", "amp_env_sustain_level", "amp_env_release_time",
                         "tone_control_bass", "tone_control_treble", "multi_effects_level", "delay_time", "delay_feedback", "delay_level",
                         "portamento_time"]),
    "VELOCITY": ("vel_", ["lfo1_rate", "lfo1_fade", "lfo2_rate", "cross_modulation_depth", "oscillator_balance", "pitch_lfo1_depth",
                          "pitch_lfo2_depth", "pitch_envelope_depth", "pitch_envelope_attack_time", "pitch_envelope_decay_time", "osc1_control1",
                          "osc1_control2", "osc2_range", "osc2_fine_wide", "osc2_control1", "osc2_control2", "cutoff_frequency", "resonance",
                          "cutoff_freq_key_follow", "filter_lfo1_depth", "filter_lfo2_depth", "filter_env_depth", "filter_env_attack_time",
                          "filter_env_decay_time", "filter_env_sus_level", "filter_env_release_time", "amp_level", "amp_lfo1_depth",
                          "amp_lfo2_depth", "amp_env_attack_time", "amp_env_decay_time", "amp_env_sustain_level", "amp_env_release_time",
                          "tone_control_bass", "tone_control_treble", "multi_effects_level", "delay_time", "delay_feedback", "delay_level",
                          "portamento_time"]),
}


def nice(s):
    s = s.replace("cutoff_freq_key_follow", "key follow").replace("_time", "").replace("_level", "").replace("envelope", "env")
    s = s.replace("oscillator", "osc").replace("cross_modulation", "x-mod").replace("multi_effects", "multi-fx").replace("control", "ctrl ")
    s = s.replace("_depth", " depth").replace("_", " ").replace("sus", "sustain").replace("ctrl  ", "ctrl ")
    return s.upper().replace("CUTOFF FREQUENCY", "CUTOFF").replace("SUSTAINTAIN", "SUSTAIN").strip()


def assign_pages(title, fn):
    """CONTROL / VELOCITY: the 40 assign depths as LCD knob cells, 16 to a sub-tab (four Q-Link rows of four), three sub-tabs."""
    pre, keys = ASSIGN[title]
    keys = [pre + k for k in keys]
    pages = []
    for sub in range(3):
        part = keys[sub * 16:(sub + 1) * 16]
        p = Page("%s %d" % (title, sub + 1), title, fn, sub)
        header(p)
        rows = [part[i:i + 4] for i in range(0, len(part), 4)]
        for r, row in enumerate(rows):
            y0 = 92 + r * 132
            p.section(16, y0, 1264, y0 + 124, None, q=True)
            for c, k in enumerate(row):
                cx = 16 + 156 + c * 312
                p.knob(k, cx - 90, y0 + 70, "", .5, D=58, show_value=False)
                art.legend(p.d, cx - 48, y0 + 44, nice(k[len(pre):]), 14, art.INK, anchor="la")
                p.value(k, cx - 48, y0 + 64, 160, 26, just="left verticallyCentred", colour="ffff6a14", size=22.0, sample="+0")
            p.qlink_group((16, y0, 1264, y0 + 124), row)
        if sub == 2:
            p.section(16, 92 + len(rows) * 132, 1264, 620, title + (" (MORPH)" if title == "CONTROL" else ""))
            msg = "CONTROL: the depth each control slider / morph sends to a parameter" if title == "CONTROL" else \
                  "VELOCITY: how much key velocity moves each parameter (VELOCITY on the EFFECTS page turns it on)"
            art.legend(p.d, 640, 92 + len(rows) * 132 + 60, msg, 15, art.INK_DIM)
        pages.append(p)
    return pages


def all_pages():
    return [main_page(), banks_page(), osc_page(), filter_page(), env_page(), fx_page(), perform_page()] + \
        assign_pages("CONTROL", 7) + assign_pages("VELOCITY", 8)
