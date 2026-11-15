#!/usr/bin/env bash
# Make tests/data/legacy-0.1.1.chunk: what a project saved with the released 0.1.1 build stores (effGetChunk), from that build's own code.
# Builds the v0.1.1 tree (engine + the mpc-vst-plugins wrapper as of the release day) for x86 as a shared library, loads it like a host
# with your ROM, and saves the chunk. Not committed: it carries ROM sound bytes. JE_ROMS: a folder with the ROM (default ~/roms/JP800015).
set -euo pipefail
cd "$(dirname "$0")/.."
MV="${MPC_VST:-$HOME/mpc-vst-plugins}"
ROMS="$(cd "${JE_ROMS:-$HOME/roms/JP800015}" && pwd)"
W=build/legacy; rm -rf "$W"; mkdir -p "$W/src" "$W/mv" "$W/plug/je8086"
git archive v0.1.1 | tar -x -C "$W/src"
MVREV="$(git -C "$MV" rev-list -1 --before=2026-11-03T17:25 HEAD)"     # the wrapper the release was built with
git -C "$MV" archive "$MVREV" wrapper tools | tar -x -C "$W/mv"
ln -s "$ROMS" "$W/plug/je8086/roms"
( cd "$W/src" && python3 ../mv/tools/gen_vst.py vst/vst.json --params-h >/dev/null )
cmake -S "$W/src" -B "$W/eng" -G Ninja -DCMAKE_BUILD_TYPE=Release -DMPC_VST="$(pwd)/$W/mv" >/dev/null
cmake --build "$W/eng" --target je8086_dsp -j"$(nproc)" >/dev/null
B="$W/eng"; libs=""
for l in libje8086_dsp.a jeLib/libjeLib.a rLib/librLib.a esp/libesp.a hardwareLib/libhardwareLib.a mc68k/lib68kEmu.a synthLib/libsynthLib.a baseLib/libbaseLib.a \
         libresample/libresample.a dsp56kBase/libdsp56kBase.a asmjit/libasmjit.a; do libs="$libs $B/$l"; done
gcc -O1 -g -fPIC -std=gnu11 -I"$W/src/vst/build" -I"$W/mv/wrapper" -c "$W/mv/wrapper/vst2_wrap.c" -o "$W/vst2_wrap.o"
g++ -shared -o "$W/plug/je8086.so" "$W/vst2_wrap.o" -Wl,--start-group $libs -Wl,--end-group -lpthread -lm -ldl
g++ -O1 -g -std=c++17 -o "$W/dump" tests/legacy_dump.cpp -ldl -lpthread
"$W/dump" "$W/plug/je8086.so" tests/data/legacy-0.1.1.chunk
