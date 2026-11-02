# Vendored source

- `gearmulator/` (framework/{baseLib,synthLib,hardwareLib}, 3rdparty/libresample, cpu/{h8s,mc68k}, cpu/dsp56300/{dsp56kBase,dsp56kEmu,asmjit,vtuneSdk},
  ronaldo/{common,esp}, ronaldo/je8086/jeLib): from https://github.com/charlesvestal/gearmulator commit `58f45e0ea6a72f82dab08144ce3079bc8e47a345` (the submodule pinned by
  schwung-je8086 `76e96e1eea5cc9192c7d320916a7f9e30cabad2a`: dsp56300/gearmulator plus its ARM64 ESP/H8S work and the threaded ASIC pipeline), with `source/cpu/dsp56300` at
  `770b86b70c351699fc9a3d67d5c08d5497d5ef53` (asmjit `3577608cab0bc509f856ebf6e41b2f9d9f71acc4`) and `source/cpu/mc68k` at `0d5dbaf3b450612a8ec11be9363727057f6fd0d3`. GPL-3.0, unmodified.
  Only the JP-8000 subset is vendored (no JUCE, no editor, no other synth); the layout is gearmulator's own, so a re-vendor is a plain copy.
  **Known:** on x86-64 this snapshot's output has a burst every 256 samples (the ESP ring, `ESP_IRAM_MIRROR`); ARM64 is clean (the target). The x86
  build is for the interface tests only.
- `skin/jeTrancy/`, `skin/parameterDescriptions_je.json`: gearmulator's `source/ronaldo/je8086/jeJucePlugin/{skins/jeTrancy,parameterDescriptions_je.json}`, unmodified.
- `src/dsp/jp8000_params.h`, `src/dsp/jp8000_banks.h`: from schwung-je8086 `76e96e1eea5cc9192c7d320916a7f9e30cabad2a` (GPL-3.0), unmodified. `tools/gen_params.py` reads the first.
- `src/dsp/je8086_engine.cpp`: ours. It drives `jeLib::Device` through `synthLib::Plugin` on a thread of MPC's own process (schwung-je8086 forks
  processes, which a VST must not); it follows schwung's boot settings, DT1 parameter writes and preset re-addressing.
