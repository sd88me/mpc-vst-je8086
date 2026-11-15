#!/usr/bin/env bash
# The release zips of the SDK build (64-bit MPCs only: gearmulator's DSP56300 JIT has no arm32 backend). Builds the release identity
# ("JE-8086", uid JE86), runs the offline tests, then packs:
#   dist/JE-8086-<ver>-mpc-aarch64.zip   Live III and other 64-bit MPCs: install.sh, the catalog / Plugin Manager zip. Same layout as
#                                        0.1.1's (je8086.so at the folder root, je8086/ beside it), so it upgrades 0.1.1 in place
#   dist/JE-8086-<ver>-mpc-sdk.zip       the same folder for copying into "VST2 Plugins" by hand (MPC OS 3.10.1+)
#   dist/JE-8086-<ver>-SHA256SUMS.txt
# The plugin finds its data as je8086/ next to its .so (as 0.1.1), so both layouts keep the ROM, banks and favourites.
# MPC_VST: an mpc-vst-plugins checkout with tools/release.py and tools/sdk_zip.py.
set -euo pipefail
cd "$(dirname "$0")/.."
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins-postlaunch}"
[ -f "$MPC_VST/tools/release.py" ] && [ -f "$MPC_VST/tools/sdk_zip.py" ] || { echo "need mpc-vst-plugins with tools/sdk_zip.py (MPC_VST)" >&2; exit 1; }
[ -n "${SKIP_BUILD:-}" ] || { ./build-sdk.sh test; ./build-sdk.sh; }
DIR="sd88me - VST - JE-8086"; SRC="build/sdk/$DIR"
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["uid"]=="JE86" and "Beta" not in m["name"] else "not the release identity")' "$SRC/plugin.json"
VER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SRC/plugin.json")
st="build/catalog/aarch64"; rm -rf "$st"; mkdir -p "$st/$DIR" "$st/data"
cp -r "$SRC/Plugin Skins" "$SRC/version.xml" "$st/$DIR/"
python3 - "$SRC/plugin.json" "$st/$DIR/plugin.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("file32", None)
m["file64"] = "je8086.so"
m["description"] = "Roland JP-8000 emulation (gearmulator JE-8086). Needs your own JP-8000 ROM in je8086/roms/."
json.dump(m, open(sys.argv[2], "w"), indent=2)
PY
cp "$SRC/VST/je8086-arm64.so" "$st/je8086.so"
cp -r release/je8086/. "$st/data/"; cp LICENSE CREDITS.md "$st/data/"
printf '<PLUGIN name="JE-8086" descriptiveName="JE-8086" format="VST" category="Synth" manufacturer="sd88me" version="%s" file="je8086.so" uid="4a453836" isInstrument="1" fileTime="0" infoUpdateTime="0" numInputs="0" numOutputs="2" isShell="0"/>\n' "$VER" > "$st/entry.xml"
python3 "$MPC_VST/tools/release.py" --so "$st/je8086.so" --skin "$st/$DIR" --entry "$st/entry.xml" --version "$VER" --extra "$st/data:je8086" \
  --user-data je8086/roms --user-data je8086/banks --user-data je8086/favourites.dat \
  --repo sd88me/mpc-vst-je8086 --license GPL-3.0-only --id je8086 --requires "your own JP-8000 ROM" \
  --about "Roland JP-8000 emulation with a native MPC skin: one LCD, BANKS browser, envelope graphs, favourites with names, tempo sync." \
  -o "$st/dist"
mkdir -p dist
z=$(ls "$st/dist"/*.zip); cp "$z" "dist/JE-8086-$VER-mpc-aarch64.zip"
python3 "$MPC_VST/tools/catalog_check.py" "dist/JE-8086-$VER-mpc-aarch64.zip" --catalog --expect-id je8086 --expect-repo sd88me/mpc-vst-je8086
python3 "$MPC_VST/tools/sdk_zip.py" "dist/JE-8086-$VER-mpc-sdk.zip" "dist/JE-8086-$VER-mpc-aarch64.zip"
for f in "dist/JE-8086-$VER-mpc-aarch64.zip" "dist/JE-8086-$VER-mpc-sdk.zip"; do   # no ROM in a release
  if python3 -I -m zipfile -l "$f" | grep -i -E '\.(bin|mid|syx|rom)\b' | grep -v "PUT_"; then echo "refusing: a ROM-like file is in $f" >&2; exit 1; fi
done
(cd dist && sha256sum "JE-8086-$VER-mpc-aarch64.zip" "JE-8086-$VER-mpc-sdk.zip" > "JE-8086-$VER-SHA256SUMS.txt" && cat "JE-8086-$VER-SHA256SUMS.txt")
