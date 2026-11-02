#!/usr/bin/env bash
# The plugin folder in MPC OS 3.10.1's own format (no MPC.settings entry, no root): copy the folder into "VST2 Plugins" at the root
# of a drive, turn on Preferences > Enhancements (Beta) > Enable Enhancements and VST2 Support, and it is listed under External VST
# Plugins. Format: the MPC plugin SDK's docs/plugin-folder-format.md (plugin.json, VST/<slug>-arm64.so, Plugin Skins/, version.xml).
#   tools/package_310.sh <version>     -> dist/VST2 Plugins/sd88me - VST - JE-8086/ and dist/JE-8086-<version>-VST2-Plugins.zip
# Run ./build.sh all first. Gen2 (arm64) only: the emulator's JIT has no 32-bit ARM backend, so there is no file32.
set -euo pipefail
cd "$(dirname "$0")/.."
VER="${1:?usage: tools/package_310.sh <version>}"
NAME="sd88me - VST - JE-8086"
OUT="dist/VST2 Plugins/$NAME"
rm -rf "dist/VST2 Plugins"; mkdir -p "$OUT/VST"
cp -r "vst/build/skin/$NAME/." "$OUT/"
cp vst/build/aarch64/je8086.so "$OUT/VST/je8086-arm64.so"
cp -r release/je8086 "$OUT/VST/je8086"           # the engine's data dir is <dir of the .so>/je8086 (roms/, banks/)
cp LICENSE CREDITS.md "$OUT/"
cat > "$OUT/plugin.json" <<JSON
{
  "name": "JE-8086",
  "manufacturer": "sd88me",
  "version": "$VER",
  "kind": "instrument",
  "uid": "JE86",
  "category": "Synth",
  "numInputs": 0,
  "numOutputs": 2,
  "file64": "VST/je8086-arm64.so",
  "description": "Roland JP-8000 emulation (gearmulator JE-8086). Needs your own JP-8000 ROM in VST/je8086/roms/.",
  "license": "GPL-3.0-only",
  "url": "https://github.com/sd88me/mpc-vst-je8086"
}
JSON
if find "$OUT" -iname "*.mid" -o -iname "*.bin" -o -iname "*.syx" | grep -q .; then echo "refusing: a ROM-like file is in the folder" >&2; exit 1; fi
(cd dist && rm -f "JE-8086-$VER-VST2-Plugins.zip" && python3 -m zipfile -c "JE-8086-$VER-VST2-Plugins.zip" "VST2 Plugins")
echo "ok: $OUT, dist/JE-8086-$VER-VST2-Plugins.zip"
