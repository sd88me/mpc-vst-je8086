# Credits and licences

JE-8086 stands on the work of others. Each licence applies to its own part; the plugin as a whole is **GPL-3.0** (`LICENSE`).

- **[gearmulator](https://github.com/dsp56300/gearmulator)** by Dieter Mueller (dsp56300) and contributors, **GPL-3.0**: the Roland JP-8000 emulation
  (`jeLib`, the ESP voice ASIC emulator and its JIT, the H8S core, `rLib`) and the support libraries (`synthLib`, `baseLib`, `hardwareLib`). "JE-8086" is
  gearmulator's name for its JP-8000 plugin. Vendored through [charlesvestal/gearmulator](https://github.com/charlesvestal/gearmulator), which carries the
  ARM64 performance and correctness work of [schwung-je8086](https://github.com/charlesvestal/schwung-je8086) (upstream PRs #293, #294, #296, #297, #300).
- **[schwung-je8086](https://github.com/charlesvestal/schwung-je8086)** by Charles Vestal, **GPL-3.0**: the JP-8000 parameter table (`src/dsp/jp8000_params.h`),
  the bank file reader (`src/dsp/jp8000_banks.h`), and the boot-time system settings and preset loading the engine follows.
- **[dsp56300](https://github.com/dsp56300/dsp56300)** (its `dsp56kBase` and `asmjit`) and **[mc68k](https://github.com/dsp56300/mc68k)**, **GPL-3.0**;
  **[AsmJit](https://github.com/asmjit/asmjit)**, **zlib**; **libresample**, BSD / LGPL.
- **The "jeTrancy" skin of JE-8086 by theusualsuspects**, **GPL-3.0** (shipped with gearmulator): the blue chassis, the "JE-8086" wordmark, the knob
  filmstrip, the panel look and its fonts Metropolis (SIL OFL 1.1) and Vipnagorgialla (baked into the page images only) (`skin/jeTrancy/`).
- **Liberation Sans** (Red Hat / Google, **SIL OFL 1.1**) for live text (`vst/fonts/`).
- **[mpc-vst-plugins](https://github.com/sd88me/mpc-vst-plugins)**: the plugin wrapper (`wrapper/vst2_wrap.c`) and the skin tools.

JE-8086 is an independent project, not affiliated with or endorsed by Roland. "JP-8000" is the name of the instrument it emulates.
No ROM is included, and none may be shared.
