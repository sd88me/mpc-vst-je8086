# JE-8086 for MPC (Gen2)

An emulation of the Roland JP-8000 as a native VST2 instrument for **Akai MPC Gen2** standalone devices (MPC Live III and kin: aarch64), with a
touchscreen skin in the look of gearmulator's JE-8086 plugin ("jeTrancy") and Q-Link control on every page. It runs the original JP-8000 firmware
on [gearmulator](https://github.com/dsp56300/gearmulator)'s H8S and ESP (voice ASIC) emulators, with the ARM64 work of
[schwung-je8086](https://github.com/charlesvestal/schwung-je8086).

**Status: 0.1.0 in development, not yet run as a plugin on a device.** The engine passes its test on an MPC Live III (MPC OS 3.9.1, run from a shell):
boots in about a second, plays, loads patches and performances, parameter edits and the saved state round trip, no dropouts, about 55-65% of one
A76 core. The plugin passes the wrapper's offline host test. Gen1 devices and the Force are not supported (the ESP JIT has no 32-bit ARM backend).

*JE-8086 is an independent project, not affiliated with or endorsed by Roland. "JP-8000" is the name of the instrument it emulates.*

## You need your own ROM
No ROM is included, and none may be shared. Put the eight JP-8000 OS update files (`_00001.mid` ... `_00008.mid`) or a full ROM `.bin` in the plugin's
`je8086/roms/`. Optional patch/performance banks (`.syx .mid .pat .pfm .j8k`) go in `je8086/banks/`.

## Install
- **MPC OS 3.10.1 and later:** `tools/package_310.sh <version>` makes `dist/VST2 Plugins/sd88me - VST - JE-8086/` (the MPC plugin SDK's folder format:
  `plugin.json`, `VST/je8086-arm64.so`, `Plugin Skins/`). Copy `VST2 Plugins` to the root of a drive, enable Preferences > Enhancements (Beta) >
  Enable Enhancements and VST2 Support, and put the ROM in `VST/je8086/roms/`.
- **Earlier MPC OS (rooted device):** the usual `MPC.settings` route of [mpc-vst-plugins](https://github.com/sd88me/mpc-vst-plugins) (`release.py` zip).

## Using it
Pages: **MAIN** (bank and patch on the LCD, edit part, key mode, voice assign, output, split, detune, tempo, gain, engine status, PANIC, RELOAD PATCH, and 16
quick-edit controls), **BANKS** (ROM patch banks A and B, the 64 performances, your bank files; 32 per page), **OSC** (LFO 1, OSC 1, OSC 2, Osc Common, Pitch
Envelope), **FILTER** (filter, filter envelope, LFO 2 modulation), **AMP** (amp, amp envelope, portamento and solo), **EFFECTS** (tone, chorus, delay),
**ARP & PARTS** (arpeggiator, upper/lower part settings), **TRIG & MORPH**, **CONTROL** and **VELOCITY** (the morph and velocity assign depths).
Notes from MPC are played on the JP-8000's panel-keyboard path, so the arpeggiator and key modes work. A program change picks a sound of the current bank.

## Building
Needs Docker, Python 3 with Pillow, and a checkout of mpc-vst-plugins (`MPC_VST`, default `~/mpc-vst-plugins`):
```
./build.sh test      # x86 engine + the wrapper's host test (ASan/UBSan)
./build.sh all       # aarch64 vst/build/aarch64/je8086.so + the skin
```
`build/<arch>/je8086_engine_test <dir with roms/>` boots the ROM and checks notes, presets, parameters and the saved state (run the aarch64 one on the device).

## Credits and licences
See [CREDITS.md](CREDITS.md). GPL-3.0 ([LICENSE](LICENSE)).
