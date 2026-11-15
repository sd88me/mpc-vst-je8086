// Offline host test for the native front end (src/JE8086Plugin.cpp) with the real engine and your ROM, under ASan/UBSan (tests/run.sh).
// A fake VST2 host drives it in real time (the emulator thread fills its ring at its own pace): identity and frozen order, a fresh
// instance's key mode / arpeggiator, sound, value / option / momentary params, the parameter-0 nudge, PANIC on a latched arp, favourites
// as programs, a state round trip into a second instance, a 0.1.1 project chunk (tests/data/legacy-0.1.1.chunk, made by the released
// build itself) handed over before the boot, a bad chunk, and a 48 kHz host. Prints OK at the end, or the failed checks and exits 1.
#include "mpc_vst2_abi.h"
#include "params_gen.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

extern "C" AEffect* VSTPluginMain(audioMasterCallback);
extern "C" void je_dbg_tick(AEffect*);
extern "C" int je_dbg_ready(AEffect*);
extern "C" int je_dbg_engine(AEffect*, const char*, char*, int);

static std::atomic<int> g_automate[kNumParams];
static std::atomic<int> g_updateDisplay{0};
static int g_fail = 0;

static VstIntPtr host(AEffect*, VstInt32 op, VstInt32 idx, VstIntPtr, void*, float)
{
    if (op == audioMasterAutomate && idx >= 0 && idx < kNumParams) g_automate[idx]++;
    if (op == audioMasterVersion) return 2400;
    if (op == audioMasterUpdateDisplay) g_updateDisplay++;
    return 0;
}

#define CHECK(c, ...) do { if (c) { std::printf("  ok   "); } else { std::printf("  FAIL "); g_fail++; } std::printf(__VA_ARGS__); std::printf("\n"); } while (0)

static int idx(const char* key)
{
    for (int i = 0; i < kNumParams; i++) if (!std::strcmp(g_pspecs[i].key, key)) return i;
    std::printf("no param %s\n", key); std::exit(2);
}
static float norm(int i, float plain) { const PSpec& s = g_pspecs[i]; return s.max > s.min ? (plain - s.min) / (s.max - s.min) : 0.f; }
static float plainOf(AEffect* e, int i) { const PSpec& s = g_pspecs[i]; return s.min + e->getParameter(e, i) * (s.max - s.min); }
static std::string eng(AEffect* e, const char* k) { char b[4096]; je_dbg_engine(e, k, b, sizeof b); return b; }
static int engi(AEffect* e, const char* k) { return std::atoi(eng(e, k).c_str()); }
static std::string disp(AEffect* e, int i) { char b[128] = {0}; e->dispatcher(e, effGetParamDisplay, i, 0, b, 0); return b; }

static double g_rms;
static void run(AEffect* e, int blocks, const std::vector<std::vector<uint8_t>>& midi = {}, int frames = 128)
{
    std::vector<float> L((size_t)frames), R((size_t)frames);
    float* out[2] = {L.data(), R.data()};
    double acc = 0; long n = 0;
    for (int b = 0; b < blocks; b++)
    {
        if (b == 0 && !midi.empty())
        {
            std::vector<VstMidiEvent> ev(midi.size());
            std::vector<char> buf(sizeof(VstEvents) + sizeof(VstEvent*) * midi.size());
            VstEvents* evs = reinterpret_cast<VstEvents*>(buf.data());
            evs->numEvents = (VstInt32)midi.size();
            for (size_t k = 0; k < midi.size(); k++)
            {
                std::memset(&ev[k], 0, sizeof ev[k]);
                ev[k].type = kVstMidiType; ev[k].byteSize = sizeof(VstMidiEvent);
                for (size_t j = 0; j < 3 && j < midi[k].size(); j++) ev[k].midiData[j] = (char)midi[k][j];
                evs->events[k] = reinterpret_cast<VstEvent*>(&ev[k]);
            }
            e->dispatcher(e, effProcessEvents, 0, 0, evs, 0);
        }
        e->processReplacing(e, nullptr, out, frames);
        for (int i = 0; i < frames; i++) { acc += (double)L[i] * L[i] + (double)R[i] * R[i]; n += 2; }
        std::this_thread::sleep_for(std::chrono::microseconds(2900 * frames / 128));
    }
    g_rms = n ? std::sqrt(acc / n) : 0;
}
static void settle(AEffect* e, int blocks = 40) { run(e, blocks); je_dbg_tick(e); }

static AEffect* open(const char* what, float rate = 44100.f)
{
    AEffect* e = VSTPluginMain(host);
    e->dispatcher(e, effSetSampleRate, 0, 0, nullptr, rate);
    e->dispatcher(e, effSetBlockSize, 0, 128, nullptr, 0);
    e->dispatcher(e, effMainsChanged, 0, 1, nullptr, 0);
    std::printf("%s: opened\n", what);
    return e;
}
static bool waitReady(AEffect* e)
{
    for (int t = 0; t < 300 && !je_dbg_ready(e); t++) run(e, 34);   // up to ~30 s
    run(e, 300);                                                       // the first sound and the temp performance arrive
    je_dbg_tick(e);
    return je_dbg_ready(e);
}
static std::vector<uint8_t> chunk(AEffect* e)
{
    void* p = nullptr;
    const VstIntPtr n = e->dispatcher(e, effGetChunk, 0, 0, &p, 0);
    return n > 0 && p ? std::vector<uint8_t>((uint8_t*)p, (uint8_t*)p + n) : std::vector<uint8_t>();
}


static void tap(AEffect* e, int i, int blocks = 300) { e->setParameter(e, i, 1.0f); settle(e, blocks); e->setParameter(e, i, 0.0f); settle(e, 20); }
extern "C" int je_dbg_kb_open(AEffect* e);
extern "C" int je_dbg_kb_name(AEffect* e, char* out, int n);
static void key(AEffect* e, const char* k) { std::this_thread::sleep_for(std::chrono::milliseconds(260)); tap(e, idx(k), 20); je_dbg_tick(e); }
static std::string kbName(AEffect* e) { char b[64] = {}; je_dbg_kb_name(e, b, sizeof b); return b; }

int main(int argc, char** argv)
{
    const char* legacyPath = argc > 1 ? argv[1] : "tests/data/legacy-0.1.1.chunk";
    const int BANK = idx("bank_index"), PRESET = idx("preset"), NEXT = idx("preset_next"), PNAME = idx("preset_name"), CUT = idx("cutoff"),
              KEY = idx("key_mode"), ARP = idx("arp_switch"), HOLD = idx("arp_hold"), PANIC = idx("all_notes_off"), GAIN = idx("gain"),
              FSAVE = idx("fav_save"), FDEL = idx("fav_delete"), SLOPE = idx("cutoff_slope");

    std::printf("== identity\n");
    AEffect* a = open("A");
    char name[64] = {0};
    a->dispatcher(a, effGetEffectName, 0, 0, name, 0);
    CHECK(a->uniqueID == (VstInt32)0x4a453836, "uid JE86 (%08x)", (unsigned)a->uniqueID);
    CHECK(!std::strcmp(name, JE_EXPECT_NAME), "name \"%s\"", name);
    CHECK(a->numParams == kNumParams && kNumParams == 306, "306 params: 0.1.1's 260 + RANDOM + the naming keyboard + INIT (%d)", a->numParams);
    CHECK(a->numPrograms == 64, "64 programs = the favourite slots (%d)", a->numPrograms);
    {
        int bad = 0, i = 0;
        FILE* f = std::fopen("params.lock", "r");
        char line[128];
        while (f && std::fgets(line, sizeof line, f))   // 234..259: the 1.x popup flags' slots (ui_open + reserved), "<key>__open" in the lock
        {
            line[std::strcspn(line, "\r\n")] = 0;
            if (!line[0]) continue;
            const bool slot = i >= kNumEngineParams && i < kNumEngineParams + kNumPopups;
            if (slot ? !std::strstr(line, "__open") : std::strcmp(line, g_pspecs[i].key) != 0) bad++;
            i++;
        }
        if (f) std::fclose(f);
        CHECK(f && bad == 0 && i == kNumParams, "order = params.lock (%d keys, %d differ)", i, bad);
        CHECK(!std::strcmp(g_pspecs[0].key, "bank_index") && !std::strcmp(g_pspecs[234].key, "ui_open"), "0 = bank_index, 234 = ui_open");
    }
    CHECK(waitReady(a), "booted (%s)", eng(a, "loading_status").c_str());

    std::printf("== a fresh instance: SINGLE, arpeggiator off\n");
    CHECK(engi(a, "key_mode") == 0 && std::lround(plainOf(a, KEY)) == 0, "KEY MODE SINGLE (engine %d, host %.0f)", engi(a, "key_mode"), plainOf(a, KEY));
    CHECK(engi(a, "arp_switch") == 0 && engi(a, "arp_hold") == 0, "ARP off, HOLD off (%d, %d)", engi(a, "arp_switch"), engi(a, "arp_hold"));

    std::printf("== sound\n");
    run(a, 200, {{0x90, 60, 100}});
    const double on = g_rms;
    run(a, 600, {{0x80, 60, 0}});
    run(a, 200);
    const double off = g_rms;
    if (on <= 1e-3) std::printf("    (silent: %s; %s; %s)\n", eng(a, "loading_status").c_str(), eng(a, "engine_stats").c_str(), eng(a, "preset_name").c_str());
    CHECK(on > 1e-3, "note on is audible (rms %.4f)", on);
    CHECK(off < on, "note off decays (rms %.4f)", off);

    std::printf("== value and option params\n");
    a->setParameter(a, CUT, norm(CUT, 64));
    settle(a, 200);
    CHECK(engi(a, "cutoff") == 64, "CUTOFF 64 -> engine %d", engi(a, "cutoff"));
    a->setParameter(a, SLOPE, 0.0f);
    settle(a, 200);
    CHECK(engi(a, "cutoff_slope") == 0 && disp(a, SLOPE) == "-12dB/oct", "SLOPE first option -> engine %d, \"%s\"", engi(a, "cutoff_slope"), disp(a, SLOPE).c_str());
    {
        const float cur = plainOf(a, CUT);
        a->setParameter(a, CUT, norm(CUT, cur) + 0.3f / 127.f);
        settle(a, 200);
        CHECK(engi(a, "cutoff") == (int)cur + 1, "a sub-step nudge up moves one step (%d -> engine %d)", (int)cur, engi(a, "cutoff"));
    }

    std::printf("== preset step, readback, text\n");
    const int p0 = engi(a, "preset");
    const std::string n0 = disp(a, PNAME);
    for (int i = 0; i < kNumParams; i++) g_automate[i] = 0;
    const int ud0 = g_updateDisplay;
    a->setParameter(a, NEXT, 1.0f);
    settle(a, 400);
    je_dbg_tick(a);
    CHECK(engi(a, "preset") == p0 + 1, "PRESET + : engine preset %d -> %d", p0, engi(a, "preset"));
    CHECK(std::lround(plainOf(a, PRESET)) == p0 + 1, "host PRESET follows (%.0f)", plainOf(a, PRESET));
    CHECK(a->getParameter(a, NEXT) == 0.f, "PRESET + dropped back to 0");
    CHECK(disp(a, PNAME) != n0, "preset name \"%s\" -> \"%s\"", n0.c_str(), disp(a, PNAME).c_str());
    int told = 0;
    for (int i = 0; i < kNumParams; i++) told += g_automate[i] > 0;
    CHECK(told > 20 && g_updateDisplay > ud0, "the host heard about the new sound (%d params, %d display updates)", told, g_updateDisplay - ud0);
    {
        int bad = 0;
        for (int i = 1; i < kNumEngineParams; i++)
        {
            const PSpec& s = g_pspecs[i];
            if (!(s.flags & kPolled)) continue;
            const int ev = std::min(std::max(engi(a, s.key), (int)s.min), (int)s.max);
            if (std::lround(plainOf(a, i)) != ev) { if (bad < 5) std::printf("    %s host %.0f engine %d\n", s.key, plainOf(a, i), engi(a, s.key)); bad++; }
        }
        CHECK(bad == 0, "every value param matches the engine after the load (%d differ)", bad);
    }

    std::printf("== parameter 0 (BANK)\n");
    const int b0 = engi(a, "bank_index");
    a->setParameter(a, 0, 1.0f); a->setParameter(a, 0, norm(0, (float)b0));
    settle(a);
    CHECK(engi(a, "bank_index") == b0, "a nudge to the end and back changes nothing (%d)", engi(a, "bank_index"));
    a->setParameter(a, BANK, norm(BANK, 2));   // the first PERF bank
    run(a, 30);
    je_dbg_tick(a);
    settle(a, 400);
    CHECK(engi(a, "bank_index") == 2, "a held change applies (bank %d, \"%s\")", engi(a, "bank_index"), eng(a, "bank_name").c_str());

    std::printf("== latched arpeggio and PANIC\n");
    a->setParameter(a, ARP, 1.0f); settle(a, 100);
    a->setParameter(a, HOLD, 1.0f); settle(a, 200);
    CHECK(engi(a, "arp_switch") == 1 && engi(a, "arp_hold") == 1, "ARP on, HOLD on (%d, %d)", engi(a, "arp_switch"), engi(a, "arp_hold"));
    tap(a, PANIC, 300);
    je_dbg_tick(a);
    CHECK(engi(a, "arp_hold") == 0 && std::lround(plainOf(a, HOLD)) == 0, "PANIC lets go of the latch (HOLD engine %d, host %.0f)", engi(a, "arp_hold"), plainOf(a, HOLD));
    a->setParameter(a, ARP, 0.0f); settle(a, 100);

    std::printf("== favourites (engine slots = programs)\n");
    {
        a->setParameter(a, KEY, 1.0f);          // SPLIT: something to see come back
        a->setParameter(a, CUT, norm(CUT, 33));
        settle(a, 300);
        const std::string fav0 = eng(a, "fav_text");
        tap(a, FSAVE, 300);
        je_dbg_tick(a);
        CHECK(je_dbg_kb_open(a) == 1 && !kbName(a).empty() && a->getParameter(a, kKbOpen) > 0.5f, "+FAV opens the keyboard on the sound's name \"%s\"", kbName(a).c_str());
        CHECK(eng(a, "fav_text") == fav0, "nothing stored until SAVE");
        for (int i = 0; i < 24 && !kbName(a).empty(); i++) key(a, "kb_bksp");
        key(a, "kb_m"); key(a, "kb_y"); key(a, "kb_space"); key(a, "kb_p"); key(a, "kb_shift"); key(a, "kb_a"); key(a, "kb_1");
        CHECK(kbName(a) == "My PA1", "typing: capital at the start and after a space, SHIFT flips one (\"%s\")", kbName(a).c_str());
        key(a, "kb_save");
        settle(a, 60); je_dbg_tick(a);
        CHECK(je_dbg_kb_open(a) == 0 && a->getParameter(a, kKbOpen) < 0.5f, "SAVE closes the keyboard");
        char pn[64] = {};
        a->dispatcher(a, effGetProgramNameIndexed, 0, 0, pn, 0);
        CHECK(eng(a, "fav_text") != fav0 && !std::strcmp(pn, "1 My PA1"), "SAVE stores it under the typed name (%s; program 1 \"%s\")", eng(a, "fav_text").c_str(), pn);
        a->setParameter(a, NEXT, 1.0f); settle(a, 400);   // another sound
        a->setParameter(a, NEXT, 0.0f); settle(a, 20);
        CHECK(engi(a, "key_mode") != 2 || engi(a, "cutoff") != 33, "another sound is loaded");
        for (int i = 0; i < 50 && engi(a, "favourite") == 0; i++) settle(a, 20);   // the load lands (favourite 1 is no longer current)
        je_dbg_tick(a);                                   // the worker follows it (program = the first empty slot)
        a->dispatcher(a, effSetProgram, 0, 0, nullptr, 0);   // the MPC's PRESET menu, favourite 1
        settle(a, 400);
        for (int i = 0; i < 100 && !(engi(a, "key_mode") == 2 && engi(a, "cutoff") == 33); i++) settle(a, 20);   // slow under ASan
        je_dbg_tick(a);
        CHECK(engi(a, "key_mode") == 2 && engi(a, "cutoff") == 33, "picking favourite 1 brings it back (key mode %d, cutoff %d)", engi(a, "key_mode"), engi(a, "cutoff"));
        tap(a, FDEL, 300);
        settle(a, 60);
        a->dispatcher(a, effGetProgramNameIndexed, 0, 0, pn, 0);
        CHECK(eng(a, "fav_text") == fav0, "-FAV removes it (%s; program 1 \"%s\")", eng(a, "fav_text").c_str(), pn);
        tap(a, FSAVE, 300); je_dbg_tick(a);
        key(a, "kb_cancel");
        settle(a, 60);
        CHECK(je_dbg_kb_open(a) == 0 && eng(a, "fav_text") == fav0, "CANCEL closes without storing (%s)", eng(a, "fav_text").c_str());
    }

    std::printf("== INIT\n");
    {
        a->setParameter(a, CUT, norm(CUT, 20)); settle(a, 200);
        tap(a, idx("init_sound"), 300); je_dbg_tick(a);
        CHECK(engi(a, "cutoff") == 127 && engi(a, "osc1_waveform") == 5 && engi(a, "amp_sustain") == 127 && std::lround(plainOf(a, CUT)) == 127,
              "INIT: a plain saw, filter open (cutoff %d, osc1 wave %d, amp sustain %d, host cutoff %.0f)", engi(a, "cutoff"),
              engi(a, "osc1_waveform"), engi(a, "amp_sustain"), plainOf(a, CUT));
    }

    std::printf("== RANDOM\n");
    {
        const int b0 = engi(a, "bank_index"), p0 = engi(a, "preset");
        tap(a, kRandom, 400); je_dbg_tick(a);
        const int b1 = engi(a, "bank_index"), p1 = engi(a, "preset");
        CHECK(b1 != b0 || p1 != p0, "RANDOM loads another sound (%d/%d -> %d/%d \"%s\")", b0, p0, b1, p1, disp(a, PNAME).c_str());
        CHECK(a->getParameter(a, kRandom) == 0.f, "RANDOM dropped back to 0");
        settle(a, 400); je_dbg_tick(a);   // let the load land before the next section edits the sound
    }

    std::printf("== state round trip\n");
    a->setParameter(a, CUT, norm(CUT, 51));
    a->setParameter(a, GAIN, norm(GAIN, 150));
    a->setParameter(a, KEY, 0.5f);   // DUAL
    settle(a, 300);
    je_dbg_tick(a);
    const std::vector<uint8_t> ca = chunk(a);
    const int ab = engi(a, "bank_index"), ap = engi(a, "preset");
    CHECK(ca.size() > 1000 && !std::memcmp(ca.data(), "MPCP", 4), "A saves an MPC chunk (%zu bytes)", ca.size());
    {
        AEffect* b = open("B");
        CHECK(b->dispatcher(b, effSetChunk, 0, (VstIntPtr)ca.size(), (void*)ca.data(), 0) == 1, "B takes A's chunk before its boot");
        const std::vector<uint8_t> early = chunk(b);
        CHECK(early.size() > 1000, "a save before the boot still holds the project's sound (%zu bytes)", early.size());
        CHECK(waitReady(b), "B booted");
        settle(b, 300); je_dbg_tick(b);
        CHECK(engi(b, "bank_index") == ab && engi(b, "preset") == ap && engi(b, "cutoff") == 51 && engi(b, "gain") == 150 && engi(b, "key_mode") == 1,
              "B has A's sound: bank %d preset %d cutoff %d gain %d key mode %d", engi(b, "bank_index"), engi(b, "preset"), engi(b, "cutoff"), engi(b, "gain"), engi(b, "key_mode"));
        CHECK(std::lround(plainOf(b, CUT)) == 51 && std::lround(plainOf(b, KEY)) == 1, "B's host values follow (cutoff %.0f, key mode %.0f)", plainOf(b, CUT), plainOf(b, KEY));
        b->dispatcher(b, effMainsChanged, 0, 0, nullptr, 0);
        b->dispatcher(b, effClose, 0, 0, nullptr, 0);
    }

    std::printf("== a project saved by 0.1.1\n");
    {
        std::vector<uint8_t> lc;
        if (FILE* f = std::fopen(legacyPath, "rb")) { int c; while ((c = std::fgetc(f)) != EOF) lc.push_back((uint8_t)c); std::fclose(f); }
        CHECK(lc.size() > 1000 && lc[0] == '{', "the 0.1.1 chunk (%zu bytes, %s)", lc.size(), legacyPath);
        AEffect* u = open("U");
        CHECK(u->dispatcher(u, effSetChunk, 0, (VstIntPtr)lc.size(), (void*)lc.data(), 0) == 1, "U takes it before its boot");
        CHECK(waitReady(u), "U booted");
        settle(u, 300); je_dbg_tick(u);
        CHECK(engi(u, "bank_index") == 2 && engi(u, "preset") == 4 && engi(u, "gain") == 180, "bank 2 preset 5 gain 180 (%d, %d, %d; \"%s\")",
              engi(u, "bank_index"), engi(u, "preset"), engi(u, "gain"), eng(u, "preset_name").c_str());
        CHECK(engi(u, "cutoff") == 40 && engi(u, "key_mode") == 1, "its edits: cutoff %d, key mode %d (40, DUAL)", engi(u, "cutoff"), engi(u, "key_mode"));
        CHECK(std::lround(plainOf(u, CUT)) == 40 && std::lround(plainOf(u, GAIN)) == 180, "host values follow (cutoff %.0f, gain %.0f)", plainOf(u, CUT), plainOf(u, GAIN));
        const char junk[] = "not a chunk";
        CHECK(u->dispatcher(u, effSetChunk, 0, sizeof junk, (void*)junk, 0) == 0, "a bad chunk is refused");
        settle(u, 60);
        CHECK(engi(u, "cutoff") == 40, "and changes nothing (%d)", engi(u, "cutoff"));
        u->dispatcher(u, effMainsChanged, 0, 0, nullptr, 0);
        u->dispatcher(u, effClose, 0, 0, nullptr, 0);
    }

    std::printf("== a 48 kHz host\n");
    {
        AEffect* h = open("H", 48000.f);
        CHECK(waitReady(h), "H booted at 48 kHz");
        run(h, 200, {{0x90, 64, 100}});
        CHECK(g_rms > 1e-3, "audible at 48 kHz (rms %.4f)", g_rms);
        run(h, 50, {{0x80, 64, 0}});
        h->dispatcher(h, effMainsChanged, 0, 0, nullptr, 0);
        h->dispatcher(h, effClose, 0, 0, nullptr, 0);
    }

    a->dispatcher(a, effMainsChanged, 0, 0, nullptr, 0);
    a->dispatcher(a, effClose, 0, 0, nullptr, 0);
    std::printf(g_fail ? "FAILED (%d)\n" : "OK\n", g_fail);
    return g_fail ? 1 : 0;
}
