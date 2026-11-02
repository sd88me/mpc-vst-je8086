/* JE-8086 for MPC: gearmulator's Roland JP-8000 emulation (jeLib: the JP-8000's H8S firmware plus its four ESP voice ASICs) as an
 * mpc-vst-plugins engine (wrapper/engine.h). GPL-3.0.
 *
 * One emulator thread per instance runs jeLib::Device through gearmulator's synthLib::Plugin (which resamples the JP-8000's
 * 88.2 kHz to the host's 44.1 kHz), fills a ring of int16 stereo, and render() only drains it. With JE_DSP_THREADS (default
 * kDefaultThreads) above 1 the device splits its four ASICs over that many threads (jeLib's JePipeline), which is what makes it
 * real time on an ARM core. Everything the host does reaches the firmware as MIDI or Roland DT1 sysex queued from the host's
 * thread: notes on the remote control channel (the panel keyboard path: arpeggiator, key mode), parameters as DT1s into the temp
 * performance, presets as their DT1s re-addressed from the user area to the temp area (what gearmulator's editor does).
 * The parameter table (address, range) is schwung-je8086's (src/dsp/jp8000_params.h); its bank reader is jp8000_banks.h.
 *
 * ROM: <data_dir>/roms/ (scanned by jeLib::RomLoader: the eight JP-8000 OS update .mid files, or a full ROM .bin). None ships.
 * User banks: <data_dir>/banks/ (.syx .mid .pat .pfm .j8k). */
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <exception>
#include <memory>
#include <mutex>
#include <string>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <thread>
#include <unistd.h>
#include <vector>

extern "C" {
#include "engine.h"
}

#include "synthLib/device.h"
#include "synthLib/midiTypes.h"
#include "synthLib/plugin.h"
#include "synthLib/romLoader.h"
#include "jeLib/device.h"
#include "jeLib/rom.h"
#include "jeLib/romloader.h"
#include "jeLib/state.h"

#include "jp8000_banks.h"
#include "jp8000_params.h"
#include "je8086_ui.h"

namespace {

constexpr int kRate = 44100, kBlock = 128;
constexpr int kRingFrames = 16384;              // power of two
constexpr int kTargetFill = 1536;               // frames the emulator thread keeps queued (~35 ms)
constexpr int kDefaultThreads = 1;              // one A76 core of a Live III runs it at ~1.7x real time; JE_DSP_THREADS=2..4 splits the ASICs (jeLib JePipeline)
constexpr int kRemoteCh = 2;                    // MIDI channel 3: the panel keyboard path (arp, key mode); see child_boot_force_system in schwung
constexpr uint32_t ADDR_TEMP = 0x01000000u;
constexpr uint32_t T_COMMON = 0x0000u, T_PART_UP = 0x1000u, T_PART_LO = 0x1100u, T_PATCH_UP = 0x4000u, T_PATCH_LO = 0x4200u;
constexpr int COMMON_LEN = 36, PART_LEN = 7, PATCH_LEN = 239;
enum { IMG_COMMON = 1, IMG_PART_UP = 2, IMG_PART_LO = 4, IMG_PATCH_UP = 8, IMG_PATCH_LO = 16, IMG_ALL = 31 };

FILE *g_log = nullptr;
void xlog(const char *fmt, ...) {
    if (!g_log) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}

/* CPU ticks of this process's threads, excluding the host's: polled every ~2 s for the STATS readout */
long emu_thread_ticks(const std::vector<long> &exclude) {
    long total = 0;
    DIR *d = opendir("/proc/self/task");
    if (!d) return 0;
    while (struct dirent *e = readdir(d)) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char path[64], line[512];
        snprintf(path, sizeof path, "/proc/self/task/%s/comm", e->d_name);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        const bool ours = fgets(line, sizeof line, f) && (strncmp(line, "JE", 2) == 0 || strncmp(line, "je", 2) == 0);
        fclose(f);
        if (!ours) continue;
        (void)exclude;
        snprintf(path, sizeof path, "/proc/self/task/%s/stat", e->d_name);
        f = fopen(path, "r");
        if (!f) continue;
        if (fgets(line, sizeof line, f)) {
            const char *q = strrchr(line, ')');
            unsigned long ut = 0, st = 0;
            if (q && sscanf(q + 2, "%*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %lu %lu", &ut, &st) == 2) total += (long)(ut + st);
        }
        fclose(f);
    }
    closedir(d);
    return total;
}

using Msg = std::vector<uint8_t>;

Msg dt1(uint32_t addr, const uint8_t *data, int n) {
    Msg m(jpbank::DT1_HEAD, jpbank::DT1_HEAD + 6);
    m.push_back((addr >> 24) & 0x7f); m.push_back((addr >> 16) & 0x7f); m.push_back((addr >> 8) & 0x7f); m.push_back(addr & 0x7f);
    m.insert(m.end(), data, data + n);
    m.push_back(jpbank::checksum(&m[6], 4 + n));
    m.push_back(0xf7);
    return m;
}

enum CmdType : uint8_t { C_MIDI, C_SYSEX, C_LOAD, C_PANIC, C_INIT, C_LOADIMG };
struct Cmd {
    CmdType type = C_MIDI;
    uint8_t m[3] = {0, 0, 0};
    int a = 0, b = 0, c = 0;
    std::vector<Msg> sx;
};

struct Image {                  // the temp performance, linear bytes
    uint8_t common[COMMON_LEN] = {};
    uint8_t part[2][PART_LEN] = {};
    uint8_t patch[2][PATCH_LEN] = {};
};

struct Inst {
    std::string dir;
    std::thread th;
    std::atomic<bool> stop{false}, ready{false}, failed{false};

    std::vector<int16_t> ring = std::vector<int16_t>(kRingFrames * 2);
    std::atomic<uint32_t> wr{0}, rd{0};
    std::atomic<uint32_t> underruns{0};
    std::atomic<int> emu_cpu{0}, threads{kDefaultThreads};

    std::mutex qm;
    std::vector<Cmd> q;

    /* UI side */
    std::atomic<int> bank{0}, preset{0}, page{0}, bank_page{0}, gain{100}, part{0};
    std::atomic<uint32_t> rev{1};
    std::mutex sm;              // everything below
    char status[96] = "Starting...";
    char rom_name[96] = "";
    std::vector<jpbank::Bank> banks;
    std::string cur_name;
    Image img;
    int img_valid = 0;

    void bump() { rev.fetch_add(1, std::memory_order_relaxed); }
    void set_status(const char *s) {
        { std::lock_guard<std::mutex> l(sm); snprintf(status, sizeof status, "%s", s); }
        bump();
    }
    void push(Cmd &&c) { std::lock_guard<std::mutex> l(qm); if (q.size() < 4096) q.push_back(std::move(c)); }
};

/* ---- the image: where a parameter lives, and DT1 replies coming back into it */

uint8_t *img_slot(Image &im, int area, int part, uint32_t *block, int *bit, int *cap) {
    switch (area) {
    case JP_AREA_PATCH: *block = part ? T_PATCH_LO : T_PATCH_UP; *bit = part ? IMG_PATCH_LO : IMG_PATCH_UP; *cap = PATCH_LEN; return im.patch[part ? 1 : 0];
    case JP_AREA_PART_UP: *block = T_PART_UP; *bit = IMG_PART_UP; *cap = PART_LEN; return im.part[0];
    case JP_AREA_PART_LO: *block = T_PART_LO; *bit = IMG_PART_LO; *cap = PART_LEN; return im.part[1];
    case JP_AREA_COMMON: *block = T_COMMON; *bit = IMG_COMMON; *cap = COMMON_LEN; return im.common;
    default: return nullptr;
    }
}

/* One DT1 from the firmware (a reply to the temp request) into the image. Returns the image bit it completed, 0 otherwise. */
int image_from_dt1(Inst *in, const Msg &m) {
    if (m.size() < 12 || memcmp(m.data(), jpbank::DT1_HEAD, 6) != 0 || m.back() != 0xf7) return 0;
    const uint32_t addr = ((uint32_t)m[6] << 24) | ((uint32_t)m[7] << 16) | ((uint32_t)m[8] << 8) | m[9];
    if ((addr >> 24) != 0x01) return 0;
    const uint32_t local = addr & 0xffff, blk = local & 0xff00;
    int area, part = 0;
    uint32_t base;
    if (blk == T_COMMON) { area = JP_AREA_COMMON; base = T_COMMON; }
    else if (blk == T_PART_UP) { area = JP_AREA_PART_UP; base = T_PART_UP; }
    else if (blk == T_PART_LO) { area = JP_AREA_PART_LO; base = T_PART_LO; }
    else if ((local & 0xfe00) == T_PATCH_UP) { area = JP_AREA_PATCH; base = T_PATCH_UP; }
    else if ((local & 0xfe00) == T_PATCH_LO) { area = JP_AREA_PATCH; base = T_PATCH_LO; part = 1; }
    else return 0;
    std::lock_guard<std::mutex> l(in->sm);
    uint32_t b; int bit, cap;
    uint8_t *dst = img_slot(in->img, area, part, &b, &bit, &cap);
    const uint32_t lin = jpbank::packed_to_linear(local - base);
    const int n = (int)m.size() - 12;
    if (lin >= (uint32_t)cap) return 0;
    const int copy = std::min<int>(n, cap - (int)lin);
    memcpy(dst + lin, &m[10], copy);
    if (lin + copy >= (uint32_t)cap) {
        in->img_valid |= bit;
        if (area == JP_AREA_PATCH && part == 0) {
            char nm[17];
            for (int i = 0; i < 16; i++) nm[i] = (char)(dst[i] >= 32 && dst[i] < 127 ? dst[i] : ' ');
            nm[16] = 0;
            for (int i = 15; i >= 0 && nm[i] == ' '; i--) nm[i] = 0;
            in->cur_name = nm;
        }
        return bit;
    }
    return 0;
}

/* The whole temp performance as five DT1s, from the image (state restore) */
std::vector<Msg> image_dt1s(const Image &im) {
    std::vector<Msg> out;
    auto add = [&](uint32_t blk, const uint8_t *d, int n) {
        for (int o = 0; o < n; o += 128) out.push_back(dt1(ADDR_TEMP | blk | jpbank::linear_to_packed(o), d + o, std::min(128, n - o)));
    };
    add(T_COMMON, im.common, COMMON_LEN);
    add(T_PART_UP, im.part[0], PART_LEN);
    add(T_PART_LO, im.part[1], PART_LEN);
    add(T_PATCH_UP, im.patch[0], PATCH_LEN);
    add(T_PATCH_LO, im.patch[1], PATCH_LEN);
    return out;
}

synthLib::SMidiEvent sysex(const Msg &m) {
    synthLib::SMidiEvent e(synthLib::MidiEventSource::Host);
    e.sysex.assign(m.begin(), m.end());
    return e;
}

void tune_thread(const char *name) {
    pthread_setname_np(pthread_self(), name);
    int nice_val = 0;
    if (const char *e = getenv("JE_NICE")) nice_val = atoi(e);
    if (nice_val) setpriority(PRIO_PROCESS, (id_t)syscall(SYS_gettid), nice_val);
}

/* ---- banks: the ROM's own (2 x 64 patches, 64 performances on a keyboard ROM) and the files in banks/ */
void build_banks(Inst *in, const jeLib::Rom &rom) {
    std::vector<std::vector<jeLib::Rom::Preset>> factory;
    rom.getPresets(factory);                                     // returns false even on success: check the sizes
    std::vector<jpbank::Bank> out;
    int perf_no = 0;
    for (size_t b = 0; b < factory.size(); b++) {
        const bool is_perf = b >= 2;
        jpbank::Bank bank;
        bank.is_perf = is_perf;
        bank.name = is_perf ? (factory.size() > 3 ? "PERF " + std::to_string(++perf_no) : std::string("PERFORMANCES")) : std::string("PATCH ") + (char)('A' + b);
        for (const auto &p : factory[b]) {
            jpbank::Preset pr;
            for (const auto &s : p) {
                Msg m(s.begin(), s.end());
                if (!jpbank::is_dt1(m)) continue;
                const uint32_t local = jpbank::dt1_addr(m) & (is_perf ? 0xffffu : 0x1ffu);
                if (local == 0 && pr.name.empty()) pr.name = jpbank::name_from(&m);
                pr.msgs.push_back(std::move(m));
            }
            if (!pr.msgs.empty()) bank.presets.push_back(std::move(pr));
        }
        if (!bank.presets.empty()) out.push_back(std::move(bank));
    }
    std::vector<jpbank::Bank> user;
    int skipped = 0;
    jpbank::scan_dir(in->dir + "/banks", user, 23, &skipped);
    for (auto &b : user) {
        for (auto &c : b.name) c = (char)toupper((unsigned char)c);
        if (b.presets.size() > 128) b.presets.resize(128);
        out.push_back(std::move(b));
    }
    if (out.size() > 64) out.resize(64);
    xlog("[banks] %zu (ROM %zu, files %zu, skipped %d)", out.size(), factory.size(), user.size(), skipped);
    std::lock_guard<std::mutex> l(in->sm);
    in->banks = std::move(out);
}

/* A preset's DT1s re-addressed to the temp performance (gearmulator's Controller::sendSingle): a patch into the edit part(s),
 * a performance as a whole */
std::vector<Msg> preset_dt1s(const jpbank::Bank &bank, const jpbank::Preset &p, int part) {
    std::vector<Msg> out;
    for (const auto &src : p.msgs) {
        Msg m = src;
        const uint32_t addr = jpbank::dt1_addr(m);
        if (bank.is_perf) {
            jpbank::dt1_set_addr(m, ADDR_TEMP | (addr & 0xffffu));
            out.push_back(m);
        } else {
            const uint32_t local = addr & 0x1ffu;
            if (part == 0 || part == 2) { jpbank::dt1_set_addr(m, ADDR_TEMP | T_PATCH_UP | local); out.push_back(m); }
            if (part == 1 || part == 2) { jpbank::dt1_set_addr(m, ADDR_TEMP | T_PATCH_LO | local); out.push_back(m); }
        }
    }
    return out;
}

/* System settings sent once at boot (schwung's child_boot_force_system, after gearmulator's editor): edit and program change
 * on, remote control channel 3 so notes take the panel keyboard path (arpeggiator, key mode), performance channel off. */
std::vector<Msg> boot_system() {
    using jeLib::State;
    using jeLib::SystemParameter;
    const std::pair<SystemParameter, int> set[] = {
        {SystemParameter::TxRxEditSwitch, 1}, {SystemParameter::TxRxEditMode, 1}, {SystemParameter::LocalSwitch, 1}, {SystemParameter::MidiSync, 1},
        {SystemParameter::KeyboardShift, 2}, {SystemParameter::TxRxProgramChangeSwitch, 0}, {SystemParameter::RemoteControlChannel, kRemoteCh},
        {SystemParameter::PerformanceControlChannel, 16}};
    std::vector<Msg> out;
    for (auto &p : set) { auto d = State::createParameterChange(p.first, p.second); out.emplace_back(d.begin(), d.end()); }
    return out;
}

Msg temp_request() {
    auto d = jeLib::State::createPerformanceRequest(jeLib::AddressArea::PerformanceTemp, jeLib::UserPerformanceArea::UserPerformance01);
    return Msg(d.begin(), d.end());
}

void emu_main(Inst *in) {
    tune_thread("JEhost");
    in->set_status("Looking for the JP-8000 ROM...");
    const std::string roms = in->dir + "/roms";
    static std::mutex rom_lock;                         // synthLib's search-path list is one global set: two instances booting at once raced on it
    jeLib::Rom rom = [&] {
        std::lock_guard<std::mutex> l(rom_lock);
        synthLib::RomLoader::addSearchPath(roms);
        return jeLib::RomLoader::findROM();
    }();
    if (!rom.isValid()) {
        in->set_status("No JP-8000 ROM in je8086/roms/ (8 OS .mid files)");
        in->failed = true;
        return;
    }
    { std::lock_guard<std::mutex> l(in->sm); snprintf(in->rom_name, sizeof in->rom_name, "%s", rom.getName().c_str()); }
    xlog("[emu] ROM %s", rom.getName().c_str());
    build_banks(in, rom);
    in->set_status("Booting the JP-8000...");

    std::unique_ptr<jeLib::Device> dev;
    std::unique_ptr<synthLib::Plugin> plugin;
    try {
        synthLib::DeviceCreateParams p;
        p.romData = rom.getData();
        p.romName = rom.getName();
        p.hostSamplerate = (float)kRate;
        p.homePath = in->dir;
        p.dspThreads = (uint32_t)in->threads.load();
        dev.reset(new jeLib::Device(p));
        plugin.reset(new synthLib::Plugin(dev.get(), [](synthLib::Device *d) { return d; }));
        plugin->setHostSamplerate((float)kRate, 0.0f);
        plugin->setBlockSize(kBlock);
    } catch (const std::exception &e) {
        char b[96];
        snprintf(b, sizeof b, "JP-8000 start failed: %.60s", e.what());
        in->set_status(b);
        in->failed = true;
        xlog("[emu] %s", b);
        return;
    }
    xlog("[emu] device created, %d DSP threads", in->threads.load());

    /* Every input and output gets a buffer of its own: synthLib::Plugin gives a missing one a scratch buffer it shares between
     * inputs and outputs, and the JP-8000 processes its audio input (the external input), so the outputs' leftovers came back
     * in as an impulse per block. Inputs stay silent. */
    static_assert(kBlock * 2 <= 512, "buffers");
    std::vector<float> zero(512, 0.0f), spare(512 * 12, 0.0f);
    float outl[512], outr[512];
    synthLib::TAudioInputs inputs = {};
    synthLib::TAudioOutputs outputs = {};
    for (auto &i : inputs) i = zero.data();
    for (size_t k = 0; k < outputs.size(); k++) outputs[k] = spare.data() + 512 * k;
    outputs[0] = outl;
    outputs[1] = outr;
    std::vector<synthLib::SMidiEvent> midiOut;
    int temp_rx = 0;                // image bits that arrived since the last temp request
    int temp_wait = -1;             // blocks since the temp request, -1 = none in flight
    long last_ticks = 0;
    auto last_t = std::chrono::steady_clock::now();
    uint32_t block_no = 0;

    auto send = [&](const Msg &m) { plugin->addMidiEvent(sysex(m)); };
    auto request_temp = [&] { temp_rx = 0; temp_wait = 0; send(temp_request()); };

    bool booted = false;            // host commands wait in the queue until the firmware is up (a restored state included)
    auto produce = [&](bool to_ring) {
        std::vector<Cmd> cmds;
        if (booted) { std::lock_guard<std::mutex> l(in->qm); cmds.swap(in->q); }
        bool reread = false;
        for (auto &c : cmds) {
            switch (c.type) {
            case C_MIDI:
                plugin->addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, c.m[0], c.m[1], c.m[2]));
                break;
            case C_SYSEX:
                for (auto &m : c.sx) send(m);
                break;
            case C_LOAD: {
                std::vector<Msg> sx;
                std::string nm;
                {
                    std::lock_guard<std::mutex> l(in->sm);
                    if (c.a >= 0 && c.a < (int)in->banks.size() && c.b >= 0 && c.b < (int)in->banks[c.a].presets.size()) {
                        sx = preset_dt1s(in->banks[c.a], in->banks[c.a].presets[c.b], c.c);
                        nm = in->banks[c.a].presets[c.b].name;
                    }
                }
                xlog("[sound] load %d/%d \"%s\" part %d (%zu DT1s)", c.a, c.b, nm.c_str(), c.c, sx.size());
                for (auto &m : sx) send(m);
                if (!sx.empty()) reread = true;
                break;
            }
            case C_LOADIMG:
                for (auto &m : c.sx) send(m);
                reread = true;
                break;
            case C_PANIC:
                for (uint8_t ch = 0; ch < 16; ch++) {
                    plugin->addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, (uint8_t)(0xb0 | ch), 123, 0));
                    plugin->addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, (uint8_t)(0xb0 | ch), 120, 0));
                }
                break;
            case C_INIT:
                break;
            }
        }
        if (reread) request_temp();
        if (temp_wait >= 0 && ++temp_wait > 2000) { xlog("[temp] no full reply (0x%x), asking again", temp_rx); request_temp(); }

        plugin->process(inputs, outputs, kBlock, 0.0f, 0.0f, false);
        block_no++;

        midiOut.clear();
        plugin->getMidiOut(midiOut);
        bool changed = false;
        for (auto &e : midiOut) {
            if (e.sysex.empty()) continue;
            const int bit = image_from_dt1(in, Msg(e.sysex.begin(), e.sysex.end()));
            if (bit) { temp_rx |= bit; changed = true; }
        }
        if (temp_wait >= 0 && (temp_rx & IMG_ALL) == IMG_ALL) temp_wait = -1;
        if (changed) in->bump();

        if (!to_ring) return;
        const float g = in->gain.load() / 100.0f * 32767.0f;
        uint32_t w = in->wr.load(std::memory_order_relaxed);
        for (int i = 0; i < kBlock; i++) {
            const float l = std::max(-32768.0f, std::min(32767.0f, outl[i] * g));
            const float r = std::max(-32768.0f, std::min(32767.0f, outr[i] * g));
            in->ring[(w & (kRingFrames - 1)) * 2] = (int16_t)l;
            in->ring[(w & (kRingFrames - 1)) * 2 + 1] = (int16_t)r;
            w++;
        }
        in->wr.store(w, std::memory_order_release);
    };

    /* boot: run until the firmware answers the temp request (the panel is up), then the first sound */
    const auto t0 = std::chrono::steady_clock::now();
    for (auto &m : boot_system()) send(m);
    request_temp();
    int boot_blocks = 0;
    const int max_boot_blocks = 60 * kRate / kBlock;            // a minute of emulated time
    while (!in->stop && boot_blocks < max_boot_blocks) {
        produce(false);
        boot_blocks++;
        if ((temp_rx & IMG_ALL) == IMG_ALL) break;
        if (boot_blocks % 690 == 0) {
            char b[96];
            snprintf(b, sizeof b, "Booting the JP-8000... %ds", boot_blocks * kBlock / kRate);
            in->set_status(b);
            if (temp_wait < 0 || temp_wait > 300) request_temp();
        }
    }
    const double boot_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    xlog("[emu] boot: %d blocks emulated (%.1f s) in %.1f s wall, image 0x%x", boot_blocks, boot_blocks * (double)kBlock / kRate, boot_s, temp_rx);
    if ((temp_rx & IMG_ALL) != IMG_ALL) {
        in->set_status("The JP-8000 firmware did not answer");
        in->failed = true;
        plugin.reset();
        dev.reset();
        return;
    }
    // single key mode on the upper part, unless a restored state (queued) sets a whole performance
    {
        bool have_state = false;
        { std::lock_guard<std::mutex> l(in->qm); for (auto &c : in->q) if (c.type == C_LOADIMG || c.type == C_LOAD) have_state = true; }
        booted = true;
        if (!have_state) {
            const uint8_t single = 0, upper = 1;
            send(dt1(ADDR_TEMP | T_COMMON | jpbank::linear_to_packed(0x10), &single, 1));
            send(dt1(ADDR_TEMP | T_COMMON | jpbank::linear_to_packed(0x12), &upper, 1));
            Cmd c; c.type = C_LOAD; c.a = in->bank.load(); c.b = in->preset.load(); c.c = 2;
            in->push(std::move(c));
        }
    }
    for (int i = 0; i < kTargetFill / kBlock + 2 && !in->stop; i++) produce(true);
    in->ready = true;
    in->set_status("Ready - ROM loaded");
    xlog("[emu] ready");

    while (!in->stop) {
        const uint32_t fill = in->wr.load(std::memory_order_relaxed) - in->rd.load(std::memory_order_acquire);
        static const bool bench = getenv("JE_BENCH") != nullptr;
        if (bench) { in->rd.store(in->wr.load()); }
        if (!bench && (fill >= (uint32_t)kTargetFill || fill + kBlock > (uint32_t)kRingFrames)) {
            std::this_thread::sleep_for(std::chrono::microseconds(500));
            continue;
        }
        produce(true);
        if ((block_no % 690) == 0) {
            const auto now = std::chrono::steady_clock::now();
            const long tk = emu_thread_ticks({});
            const double dt = std::chrono::duration<double>(now - last_t).count();
            if (dt > 0.1) in->emu_cpu = (int)((tk - last_ticks) / 100.0 / dt * 100.0);
            if (bench) xlog("[bench] %.2fx real time, emu cpu %d%%", 690.0 * kBlock / kRate / dt, in->emu_cpu.load());
            last_ticks = tk;
            last_t = now;
        }
    }
    xlog("[emu] stopping");
    plugin.reset();
    dev.reset();
}

/* ------------------------------------------------------------------ the engine interface */

const jp_param_t *find_param(const char *key) {
    for (int i = 0; i < JP_PARAM_COUNT; i++)
        if (!strcmp(jp_params[i].key, key)) return &jp_params[i];
    return nullptr;
}
const je_opts_t *find_opts(const char *key) {
    for (int i = 0; i < JE_NUM_OPTS; i++)
        if (!strcmp(je_opts[i].key, key)) return &je_opts[i];
    return nullptr;
}

int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

void *eng_create(const char *dir) {
    if (!g_log) g_log = fopen(getenv("JE_LOG") ? getenv("JE_LOG") : "/tmp/je8086.log", "a");
    Inst *in = new Inst();
    in->dir = dir ? dir : "";
    if (const char *t = getenv("JE_DSP_THREADS")) in->threads = clampi(atoi(t), 1, 4);
    in->th = std::thread(emu_main, in);
    return in;
}

void eng_destroy(void *p) {
    Inst *in = (Inst *)p;
    if (!in) return;
    in->stop = true;
    if (in->th.joinable()) in->th.join();
    delete in;
}

int bank_count(Inst *in) { std::lock_guard<std::mutex> l(in->sm); return (int)in->banks.size(); }
int preset_count(Inst *in, int b) {
    std::lock_guard<std::mutex> l(in->sm);
    return b >= 0 && b < (int)in->banks.size() ? (int)in->banks[b].presets.size() : 0;
}

void select_sound(Inst *in, int bank, int prog) {
    const int nb = bank_count(in);
    bank = nb > 0 ? clampi(bank, 0, nb - 1) : clampi(bank, 0, 63);      // no bank list yet (no ROM): keep what was asked
    const int np = preset_count(in, bank);
    prog = np > 0 ? clampi(prog, 0, np - 1) : clampi(prog, 0, 127);
    in->bank = bank;
    in->preset = prog;
    in->page = prog / JE_PATCH_TILES;
    Cmd c;
    c.type = C_LOAD;
    c.a = bank;
    c.b = prog;
    c.c = in->part.load();
    in->push(std::move(c));
    in->bump();
}

void eng_midi(void *p, const uint8_t *msg, int len) {
    Inst *in = (Inst *)p;
    if (!in || len < 1 || len > 3 || msg[0] < 0x80 || msg[0] >= 0xf0) return;
    const uint8_t st = msg[0] & 0xf0;
    if (st == 0xc0 && len >= 2) { select_sound(in, in->bank, msg[1]); return; }
    if (st == 0xb0 && len >= 3 && (msg[1] == 0 || msg[1] == 32)) {     // bank select: takes effect with the next program change
        if (msg[1] == 0 && msg[2] < bank_count(in)) in->bank = msg[2];
        return;
    }
    Cmd c;
    c.type = C_MIDI;
    c.m[0] = (uint8_t)(st | kRemoteCh);
    c.m[1] = len > 1 ? msg[1] : 0;
    c.m[2] = len > 2 ? msg[2] : 0;
    in->push(std::move(c));
}

int slot_key(const char *key, const char *prefix, int max, bool *on) {
    const size_t n = strlen(prefix);
    if (strncmp(key, prefix, n) != 0) return 0;
    char *end = nullptr;
    const long v = strtol(key + n, &end, 10);
    if (end == key + n || v < 1 || v > max) return 0;
    if (*end == 0) { *on = false; return (int)v; }
    if (strcmp(end, "_on") == 0) { *on = true; return (int)v; }
    return 0;
}

int hexval(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }

void write_param(Inst *in, const jp_param_t *q, int value) {
    int raw = q->neg ? -value : value + q->off;
    raw = clampi(raw, 0, q->bit14 ? 16383 : 127);
    uint8_t data[2];
    int n;
    if (q->bit14) { data[0] = (raw >> 7) & 0x7f; data[1] = raw & 0x7f; n = 2; }
    else { data[0] = raw & 0x7f; n = 1; }
    Cmd c;
    c.type = C_SYSEX;
    const int part = in->part.load();
    std::lock_guard<std::mutex> l(in->sm);
    for (int pt = 0; pt < 2; pt++) {
        if (q->area == JP_AREA_PATCH && !(part == 2 || part == pt)) continue;
        if (q->area != JP_AREA_PATCH && pt) break;
        uint32_t block; int bit, cap;
        uint8_t *img = img_slot(in->img, q->area, pt, &block, &bit, &cap);
        if (!img || q->lin + n > cap) return;
        memcpy(img + q->lin, data, n);
        c.sx.push_back(dt1(ADDR_TEMP | block | jpbank::linear_to_packed(q->lin), data, n));
    }
    in->push(std::move(c));
}

int read_param(Inst *in, const jp_param_t *q, int *value) {
    std::lock_guard<std::mutex> l(in->sm);
    uint32_t block; int bit, cap;
    const int pt = (q->area == JP_AREA_PATCH && in->part.load() == 1) ? 1 : 0;
    const uint8_t *img = img_slot(in->img, q->area, pt, &block, &bit, &cap);
    if (!img || q->lin + (q->bit14 ? 2 : 1) > cap) return -1;
    int raw = img[q->lin];
    if (q->bit14) raw = (raw << 7) | img[q->lin + 1];
    *value = q->neg ? -raw : raw - q->off;
    return 0;
}

void restore_state(Inst *in, const char *s) {
    auto num = [&](const char *k, int def) {
        const char *q = strstr(s, k);
        return q ? atoi(q + strlen(k)) : def;
    };
    in->bank = std::max(0, num("\"bank\":", 0));
    in->preset = std::max(0, num("\"preset\":", 0));
    in->page = in->preset / JE_PATCH_TILES;
    in->gain = clampi(num("\"gain\":", 100), 10, 400);
    in->part = clampi(num("\"part\":", 0), 0, 2);
    const char *h = strstr(s, "\"img\":\"");
    if (h) {
        h += 7;
        std::vector<uint8_t> d;
        while (hexval(h[0]) >= 0 && hexval(h[1]) >= 0) { d.push_back((uint8_t)(hexval(h[0]) * 16 + hexval(h[1]))); h += 2; }
        if (d.size() == sizeof(Image)) {
            Image im;
            memcpy(&im, d.data(), sizeof im);
            { std::lock_guard<std::mutex> l(in->sm); in->img = im; }
            Cmd c;
            c.type = C_LOADIMG;
            c.sx = image_dt1s(im);
            in->push(std::move(c));
            in->bump();
            return;
        }
    }
    select_sound(in, in->bank, in->preset);
}

void eng_set(void *p, const char *key, const char *val) {
    Inst *in = (Inst *)p;
    if (!in || !key || !val) return;
    bool on = false;
    int n;
    const bool press = atoi(val) != 0;
    if ((n = slot_key(key, "bank_slot_", JE_BANK_TILES, &on)) && !on) {
        const int b = in->bank_page * JE_BANK_TILES + n - 1;
        if (press && b < bank_count(in)) select_sound(in, b, 0);
        return;
    }
    if ((n = slot_key(key, "patch_slot_", JE_PATCH_TILES, &on)) && !on) {
        const int i = in->page * JE_PATCH_TILES + n - 1;
        if (press && i < preset_count(in, in->bank)) select_sound(in, in->bank, i);
        return;
    }
    const int pages = std::max(1, (preset_count(in, in->bank) + JE_PATCH_TILES - 1) / JE_PATCH_TILES);
    const int bpages = std::max(1, (bank_count(in) + JE_BANK_TILES - 1) / JE_BANK_TILES);
    if (!strcmp(key, "patch_page_prev")) { if (press && in->page > 0) { in->page--; in->bump(); } return; }
    if (!strcmp(key, "patch_page_next")) { if (press && in->page + 1 < pages) { in->page++; in->bump(); } return; }
    if (!strcmp(key, "bank_page_prev")) { if (press && in->bank_page > 0) { in->bank_page--; in->bump(); } return; }
    if (!strcmp(key, "bank_page_next")) { if (press && in->bank_page + 1 < bpages) { in->bank_page++; in->bump(); } return; }
    if (!strcmp(key, "preset")) { select_sound(in, in->bank, atoi(val)); return; }
    if (!strcmp(key, "bank_index")) { select_sound(in, atoi(val), 0); return; }
    if (!strcmp(key, "preset_next") || !strcmp(key, "preset_prev")) {
        const int np = preset_count(in, in->bank);
        if (press && np > 0) select_sound(in, in->bank, (in->preset + (!strcmp(key, "preset_next") ? 1 : np - 1)) % np);
        return;
    }
    if (!strcmp(key, "bank_next") || !strcmp(key, "bank_prev")) {
        const int nb = bank_count(in);
        if (press && nb > 0) {
            const int b = (in->bank + (!strcmp(key, "bank_next") ? 1 : nb - 1)) % nb;
            in->bank_page = b / JE_BANK_TILES;
            select_sound(in, b, 0);
        }
        return;
    }
    if (!strcmp(key, "all_notes_off")) { if (press) { Cmd c; c.type = C_PANIC; in->push(std::move(c)); } return; }
    if (!strcmp(key, "init_patch")) { if (press) select_sound(in, in->bank, in->preset); return; }      // reload the stored preset
    if (!strcmp(key, "gain")) { in->gain = clampi(atoi(val), 10, 400); return; }
    if (!strcmp(key, "edit_part")) {
        static const char *const parts[] = {"UPPER", "LOWER", "BOTH"};
        for (int i = 0; i < 3; i++) if (!strcmp(val, parts[i])) in->part = i;
        if (isdigit((unsigned char)val[0])) in->part = clampi(atoi(val), 0, 2);
        in->bump();
        return;
    }
    if (!strcmp(key, "state")) { restore_state(in, val); return; }
    const jp_param_t *q = find_param(key);
    if (!q) return;
    int v = atoi(val);
    if (const je_opts_t *o = find_opts(key)) {          // the wrapper sends an option's index as a number; a label also works
        if (!isdigit((unsigned char)val[0]) && val[0] != '-')
            for (int i = 0; i < o->n; i++) if (!strcmp(val, o->labels[i])) v = i;
        v += q->vmin;
    }
    write_param(in, q, clampi(v, q->vmin, q->vmax));
}

int put(char *buf, int n, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    const int r = vsnprintf(buf, n, fmt, ap);
    va_end(ap);
    return r < 0 ? 0 : std::min(r, n - 1);
}

int eng_get(void *p, const char *key, char *buf, int n) {
    Inst *in = (Inst *)p;
    if (!in || !key || n < 2) return -1;
    bool on = false;
    int k;
    if ((k = slot_key(key, "bank_slot_", JE_BANK_TILES, &on))) {
        const int b = in->bank_page * JE_BANK_TILES + k - 1;
        if (on) return put(buf, n, "%d", b == in->bank ? 1 : 0);
        std::lock_guard<std::mutex> l(in->sm);
        return put(buf, n, "%s", b < (int)in->banks.size() ? in->banks[b].name.c_str() : "");
    }
    if ((k = slot_key(key, "patch_slot_", JE_PATCH_TILES, &on))) {
        const int idx = in->page * JE_PATCH_TILES + k - 1;
        if (on) return put(buf, n, "%d", idx == in->preset ? 1 : 0);
        std::lock_guard<std::mutex> l(in->sm);
        const int b = in->bank;
        if (b >= (int)in->banks.size() || idx >= (int)in->banks[b].presets.size()) return put(buf, n, "%s", "");
        return put(buf, n, "%03d %s", idx + 1, in->banks[b].presets[idx].name.c_str());
    }
    if (!strcmp(key, "patch_page_text")) return put(buf, n, "PAGE %d / %d", in->page + 1, std::max(1, (preset_count(in, in->bank) + JE_PATCH_TILES - 1) / JE_PATCH_TILES));
    if (!strcmp(key, "bank_page_text")) return put(buf, n, "%d / %d", in->bank_page + 1, std::max(1, (bank_count(in) + JE_BANK_TILES - 1) / JE_BANK_TILES));
    if (!strcmp(key, "preset")) return put(buf, n, "%d", in->preset.load());
    if (!strcmp(key, "bank_index")) return put(buf, n, "%d", in->bank.load());
    if (!strcmp(key, "bank_name")) {
        std::lock_guard<std::mutex> l(in->sm);
        const int b = in->bank;
        return put(buf, n, "%s", b < (int)in->banks.size() ? in->banks[b].name.c_str() : "-");
    }
    if (!strcmp(key, "preset_name")) {
        std::lock_guard<std::mutex> l(in->sm);
        const int b = in->bank, pr = in->preset;
        const bool perf = b < (int)in->banks.size() && in->banks[b].is_perf;
        const char *nm = (!perf && !in->cur_name.empty()) ? in->cur_name.c_str()
                       : (b < (int)in->banks.size() && pr < (int)in->banks[b].presets.size() ? in->banks[b].presets[pr].name.c_str() : "");
        return put(buf, n, "%03d %s", pr + 1, nm);
    }
    if (!strcmp(key, "rom_name")) { std::lock_guard<std::mutex> l(in->sm); return put(buf, n, "%s", in->rom_name[0] ? in->rom_name : "-"); }
    if (!strcmp(key, "loading_status")) { std::lock_guard<std::mutex> l(in->sm); return put(buf, n, "%s", in->status); }
    if (!strcmp(key, "engine_stats")) return put(buf, n, "DROPOUTS %u   CPU %d%%   %d THREADS", in->underruns.load(), in->emu_cpu.load(), in->threads.load());
    if (!strcmp(key, "gain")) return put(buf, n, "%d", in->gain.load());
    if (!strcmp(key, "edit_part")) return put(buf, n, "%d", clampi(in->part, 0, 2));
    if (!strcmp(key, "display_rev")) return put(buf, n, "%u", in->rev.load());
    if (!strcmp(key, "state")) {
        std::lock_guard<std::mutex> l(in->sm);
        int off = put(buf, n, "{\"state_version\":1,\"bank\":%d,\"preset\":%d,\"gain\":%d,\"part\":%d", in->bank.load(), in->preset.load(), in->gain.load(), in->part.load());
        if ((in->img_valid & IMG_ALL) == IMG_ALL && off + (int)sizeof(Image) * 2 + 16 < n) {
            off += put(buf + off, n - off, ",\"img\":\"");
            static const char hx[] = "0123456789abcdef";
            const uint8_t *b = (const uint8_t *)&in->img;
            for (size_t i = 0; i < sizeof(Image); i++) { buf[off++] = hx[b[i] >> 4]; buf[off++] = hx[b[i] & 15]; }
            buf[off] = 0;
            off += put(buf + off, n - off, "\"");
        }
        off += put(buf + off, n - off, "}");
        return off;
    }
    const jp_param_t *q = find_param(key);
    if (q) {
        int v;
        if (read_param(in, q, &v) != 0) v = q->def;
        // an option list answers with its index: the wrapper reads a number first, and labels such as "5-3" would parse as one
        if (const je_opts_t *o = find_opts(key)) return put(buf, n, "%d", clampi(v - q->vmin, 0, o->n - 1));
        return put(buf, n, "%d", v);
    }
    return -1;
}

void eng_render(void *p, int16_t *out, int frames) {
    Inst *in = (Inst *)p;
    if (!in || !in->ready.load(std::memory_order_acquire)) { memset(out, 0, (size_t)frames * 4); return; }
    uint32_t r = in->rd.load(std::memory_order_relaxed);
    const uint32_t avail = in->wr.load(std::memory_order_acquire) - r;
    const int got = (int)std::min<uint32_t>(avail, (uint32_t)frames);
    for (int i = 0; i < got; i++, r++) {
        out[i * 2] = in->ring[(r & (kRingFrames - 1)) * 2];
        out[i * 2 + 1] = in->ring[(r & (kRingFrames - 1)) * 2 + 1];
    }
    in->rd.store(r, std::memory_order_release);
    if (got < frames) {
        memset(out + got * 2, 0, (size_t)(frames - got) * 4);
        in->underruns.fetch_add(1, std::memory_order_relaxed);
    }
}

const mpc_engine_t engine = {eng_create, eng_destroy, eng_midi, eng_set, eng_get, eng_render, nullptr, nullptr};

}  // namespace

extern "C" const mpc_engine_t *mpc_engine(void) { return &engine; }
