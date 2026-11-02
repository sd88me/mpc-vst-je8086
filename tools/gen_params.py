#!/usr/bin/env python3
"""Write vst/params.json and src/dsp/je8086_ui.h from src/dsp/jp8000_params.h (schwung-je8086's table, itself generated from
gearmulator's parameterDescriptions_je.json). VST index = order: engine keys first, then the JP-8000's own parameters in table
order, then everything added later. Append only (vst/params.lock is checked by gen_vst.py)."""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDR_IN = os.path.join(ROOT, "src/dsp/jp8000_params.h")
OUT = os.path.join(ROOT, "vst/params.json")
HDR = os.path.join(ROOT, "src/dsp/je8086_ui.h")

s = open(HDR_IN).read()
m = re.search(r'jp_chain_params_prefix\[\] =\s*((?:"(?:[^"\\]|\\.)*"\s*)+);', s)
chain = json.loads("".join(json.loads(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"', m.group(1))) + "]")
table = re.findall(r'\{"(\w+)", (\d+), 0x[0-9a-f]+, (\d), (-?\d+), (-?\d+), (-?\d+), (-?\d+), (\d+), (\d)\}', s)
area = {k: int(a) for k, a, *_ in table}

params, keys_in = [], {}
def add(p, sec):
    params.append(p)
    keys_in.setdefault(sec, []).append(p["key"])

N_BANK_TILES, N_PATCH_TILES = 8, 32
add(dict(key="bank_index", name="BANK", min=0, max=63, default=0, display="int"), "Browse")
add(dict(key="preset", name="PRESET", min=0, max=127, default=0, display="int"), "Browse")
add(dict(key="bank_name", name="BANK NAME", min=0, max=0, default=0, display="string", poll=True), "Browse")
add(dict(key="preset_name", name="PRESET NAME", min=0, max=0, default=0, display="string", poll=True), "Browse")
add(dict(key="bank_prev", name="BANK -", min=0, max=1, default=0, momentary=True), "Browse")
add(dict(key="bank_next", name="BANK +", min=0, max=1, default=0, momentary=True), "Browse")
add(dict(key="preset_prev", name="PRESET -", min=0, max=1, default=0, momentary=True), "Browse")
add(dict(key="preset_next", name="PRESET +", min=0, max=1, default=0, momentary=True), "Browse")
add(dict(key="all_notes_off", name="PANIC", min=0, max=1, default=0, momentary=True), "Browse")
add(dict(key="rom_name", name="ROM", min=0, max=0, default=0, display="string", poll=True), "System")
add(dict(key="loading_status", name="STATUS", min=0, max=0, default=0, display="string", poll=True), "System")
add(dict(key="engine_stats", name="STATS", min=0, max=0, default=0, display="string", poll=True), "System")
add(dict(key="gain", name="GAIN %", min=10, max=400, default=100, display="int"), "System")
add(dict(key="init_patch", name="INIT", min=0, max=1, default=0, momentary=True), "System")
add(dict(key="edit_part", name="EDIT PART", options=["UPPER", "LOWER", "BOTH"], default="UPPER", refresh_display=True), "System")

SKIP = {"mode", "buffer_ms", "part"}
SECTION = [("ctl_", "Control"), ("vel_", "Velocity"), ("active_", "Velocity"), ("up_", "Parts"), ("lo_", "Parts"), ("sys_", "System Setup"),
           ("lfo", "LFO"), ("osc", "Osc"), ("ring", "Osc"), ("cross", "Osc"), ("pitch", "Osc"), ("filter", "Filter"), ("cutoff", "Filter"),
           ("resonance", "Filter"), ("key_follow", "Filter"), ("amp", "Amp"), ("tone", "Effects"), ("chorus", "Effects"), ("delay", "Effects"),
           ("arp", "Arp"), ("trigger", "Arp"), ("tempo", "Arp")]
def section(k):
    for p, sec in SECTION:
        if k.startswith(p): return sec
    return "Common"

jp_keys = []
for c in chain:
    k = c["key"]
    if k in SKIP or k.startswith("sys_") or k not in area:
        continue
    name = c["name"].upper()
    if c["type"] == "enum":
        opts = c["options"]
        if len(set(opts)) != len(opts):          # duplicate labels confuse the label -> index mapping
            opts = ["%s" % o if opts.count(o) == 1 else "%s %d" % (o, i) for i, o in enumerate(opts)]
        d = c.get("default", 0)
        p = dict(key=k, name=name, options=opts, default=opts[d if isinstance(d, int) and 0 <= d < len(opts) else 0])
    else:
        p = dict(key=k, name=name, min=c["min"], max=c["max"], default=c.get("default", 0), display="int")
    add(p, section(k))
    jp_keys.append(k)

for i in range(1, N_BANK_TILES + 1):
    add(dict(key="bank_slot_%d" % i, name="BANK %d" % i, min=0, max=1, default=0, momentary=True, display="string", poll=True), "Banks")
add(dict(key="bank_page_text", name="BANK PAGE", min=0, max=0, default=0, display="string", poll=True), "Banks")
add(dict(key="bank_page_prev", name="BANK PAGE -", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="bank_page_next", name="BANK PAGE +", min=0, max=1, default=0, momentary=True), "Banks")
for i in range(1, N_PATCH_TILES + 1):
    add(dict(key="patch_slot_%d" % i, name="PATCH %d" % i, min=0, max=1, default=0, momentary=True, display="string", poll=True), "Banks")
add(dict(key="patch_page_text", name="PAGE", min=0, max=0, default=0, display="string", poll=True), "Banks")
add(dict(key="patch_page_prev", name="PAGE -", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="patch_page_next", name="PAGE +", min=0, max=1, default=0, momentary=True), "Banks")

# favourites (appended last: saved projects bind by index): "favourite" is MPC's native program list (vst.json "programs")
add(dict(key="favourite", name="FAVOURITE", min=0, max=63, default=63, display="int"), "Banks")
add(dict(key="fav_save", name="SAVE FAV", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="fav_delete", name="DEL FAV", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="fav_text", name="FAVOURITES", min=0, max=0, default=0, display="string", poll=True), "Banks")

order = ["Browse", "Banks", "System", "Osc", "Filter", "Amp", "LFO", "Effects", "Common", "Arp", "Parts", "Control", "Velocity"]
sections = [{"label": s, "keys": keys_in[s]} for s in order if s in keys_in]
json.dump({"name": "JE-8086", "params": params, "sections": sections}, open(OUT, "w"), indent=1)

with open(HDR, "w") as f:
    f.write("/* generated by tools/gen_params.py: do not edit. */\n#pragma once\n")
    f.write("#define JE_BANK_TILES %d\n#define JE_PATCH_TILES %d\n" % (N_BANK_TILES, N_PATCH_TILES))
    # option labels of every enum key, so the engine can answer with the text the wrapper maps back to an index
    f.write("struct je_opts_t { const char *key; int n; const char *const *labels; };\n")
    rows = []
    for p in params:
        if "options" in p and p["key"] in jp_keys:
            cid = "je_o_" + p["key"]
            f.write("static const char *const %s[] = {%s};\n" % (cid, ",".join(json.dumps(o) for o in p["options"])))
            rows.append('{"%s",%d,%s}' % (p["key"], len(p["options"]), cid))
    f.write("static const je_opts_t je_opts[] = {%s};\n#define JE_NUM_OPTS %d\n" % (",\n ".join(rows), len(rows)))
print("params:", len(params), "jp:", len(jp_keys))
