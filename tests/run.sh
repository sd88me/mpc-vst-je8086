#!/usr/bin/env bash
# Offline x86 test under ASan/UBSan (no device): the native front end + the real engine and your ROM, driven by tests/host_test.cpp in
# real time. Must print OK. JE_ROMS: a folder with your JP-8000 ROM (default ~/roms/JP800015). JE_NAME: the build's name (beta tests).
set -euo pipefail
cd "$(dirname "$0")/.."
SDK="${MPC_SDK:-$HOME/mpc-plugin-builder-sdk}"
[ -f "$SDK/framework/mpc_plugin.h" ] || [ -n "${MPC_SDK:-}" ] || SDK="$HOME/mpc-310-private/mpc-plugin-builder-sdk"   # its older place
MV="${MPC_VST:-$HOME/mpc-vst-plugins}"
ROMS="$(cd "${JE_ROMS:-$HOME/roms/JP800015}" && pwd)"
python3 tools/gen_sdk_params.py >/dev/null
# A project chunk saved by the released 0.1.1 build, made from that build's own code and your ROM (not committed: it holds a ROM sound).
[ -f tests/data/legacy-0.1.1.chunk ] || JE_ROMS="$ROMS" tests/make_legacy_chunk.sh >/dev/null 2>&1
# the engine (unsanitised, Release) for x86, in its own build dir: vst/build/engine/ holds the aarch64 archive
cmake -S . -B build/x86 -G Ninja -DCMAKE_BUILD_TYPE=Release -DMPC_VST="$MV" >/dev/null
cmake --build build/x86 --target je8086_dsp -j"$(nproc)" > build/engine-x86.log 2>&1 || { grep -E "error" build/engine-x86.log | head -20; exit 1; }
B=build/x86; libs=""
for l in libje8086_dsp.a jeLib/libjeLib.a rLib/librLib.a esp/libesp.a hardwareLib/libhardwareLib.a mc68k/lib68kEmu.a synthLib/libsynthLib.a baseLib/libbaseLib.a libresample/libresample.a dsp56kBase/libdsp56kBase.a asmjit/libasmjit.a; do libs="$libs $B/$l"; done
T=build/test; mkdir -p "$T"
S="-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -O1 -g -std=c++17 -pthread"
N="${JE_NAME:-JE-8086}"
g++ $S -Wall -Wextra -DJE_TEST -DJE_NAME="\"$N\"" -I"$SDK/framework" -I"$MV/wrapper" -Isrc -c src/JE8086Plugin.cpp -o "$T/plugin.o"
g++ $S -DJE_EXPECT_NAME="\"$N\"" -I"$SDK/framework" -Isrc -c tests/host_test.cpp -o "$T/host_test.o"
g++ $S -o "$T/jetest" "$T/plugin.o" "$T/host_test.o" -Wl,--start-group $libs -Wl,--end-group -ldl -lm
pf="$(mktemp -d)"; trap 'rm -rf "$pf"' EXIT
mkdir -p "$pf/je8086"; cp -r "$ROMS" "$pf/je8086/roms"; cp plugin.json "$pf/"
set +e
MPC_PLUGIN_FOLDER="$pf" ASAN_OPTIONS=detect_leaks=1 "$T/jetest" tests/data/legacy-0.1.1.chunk > "$T/log.txt" 2>&1
st=$?
grep -E '^(== |  ok   |  FAIL |OK$|FAILED|[A-DUW]: opened|    \(|    [A-Za-z0-9_]+ host )|ERROR: |runtime error' "$T/log.txt" | tail -${TAIL:-120}
exit $st
