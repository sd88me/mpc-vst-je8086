# JE-8086 1.0.0

Rebuilt on the MPC Plugin SDK, with a new native skin.

## New
- **New skin** in the JP-8000's look: one LCD on MAIN instead of many small readouts, big knobs, long faders, rubber keys with LEDs.
  Pages: MAIN, BANKS, OSC, FILTER / AMP, ENVELOPES, EFFECTS, PERFORM, CONTROL, VELOCITY.
- **Envelope graphs** on the ENVELOPES page: drag the handles, or use the faders under them.
- **Name your favourites:** +FAV opens an on-screen keyboard; the name shows in MPC's PRESET menu.
- **RANDOM** on BANKS picks a sound from every bank.
- **INIT** on MAIN gives a plain starting sound.
- **Tempo sync:** the arpeggiator and the synced delay, chorus and LFO follow MPC's tempo.

## Changed
- A new instance starts in SINGLE key mode with the panel on both parts, and the arpeggiator and HOLD off (0.1.x could start in DUAL with a
  latched arpeggio).
- PANIC also lets go of a held arpeggio.
- The CPU / dropout readout keeps updating while favourites are listed.

## Upgrading
Install over 0.1.x (merge the folder, don't delete it first): your ROM, banks and favourites stay. Projects saved with 0.1.x load with their
sound, edits and Q-Link assignments.

## Install
- `JE-8086-1.0.0-mpc-aarch64.zip`: for the Plugin Manager, the catalog, or `install.sh` on the device as root.
- `JE-8086-1.0.0-mpc-sdk.zip`: one folder to copy into `VST2 Plugins` by hand.

64-bit MPCs (Live III and other Gen2 devices) with MPC OS 3.10 or later. Needs your own JP-8000 ROM.

**Checked:** offline tests (ASan/UBSan: parameters, favourites and the naming keyboard, RANDOM, INIT, tempo, 0.1.1 projects) and on an MPC
Live III with a beta of this code.
