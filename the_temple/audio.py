"""Synthesized location sound through a 1987 camcorder microphone.

Optional dialogue: drop mono/stereo WAVs named after the subtitle ids
(officer_1.wav, officer_2.wav, guide_1.wav, researcher_1.wav, leader_1.wav)
into ./vo/ and they are mixed in at the subtitle times, through the same
room acoustics and mic chain.
"""
import os
import wave

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from common import CUT_TO_BLACK, DUR, HERE, SCENES, SUBTITLES, gust

SR = 48000
N = int(SR * DUR)
rng = np.random.default_rng(77)


def noise(n):
    return rng.standard_normal(n)


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, kind, fs=SR, output="sos"), x)


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def place(buf, sig, t0, gain=1.0):
    i = int(t0 * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    buf[i:i + len(sig)] += gain * sig


# ---------------------------------------------------------------------------
# Sound sources
# ---------------------------------------------------------------------------
def click():
    n = int(0.03 * SR)
    return filt(noise(n), "highpass", 2000) * env(n, 0.0003, 0.004) + \
        np.sin(2 * np.pi * 3100 * np.arange(n) / SR) * env(n, 0.0003, 0.006) * 0.5


def thud(f=80, dur=0.5, amt=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(f * (1 + 1.5 * np.exp(-t / 0.02))) / SR
    return amt * (np.sin(ph) * env(n, 0.002, dur / 4) + 0.5 * filt(noise(n), "lowpass", 400) * env(n, 0.001, 0.05))


def clack(pitch=1.0, amt=1.0):
    n = int(0.25 * SR)
    out = np.zeros(n)
    for f, d in ((900, 0.03), (1700, 0.02), (2600, 0.015), (420, 0.05)):
        out += filt(noise(n), "bandpass", [f * pitch * 0.9, f * pitch * 1.1]) * env(n, 0.0005, d)
    return amt * out * 3


def crunch(amt=1.0):
    n = int(0.18 * SR)
    grains = (rng.random(n) > 0.985) * rng.random(n)
    g = filt(grains, "bandpass", [700, 6000]) * 6 + filt(noise(n), "bandpass", [300, 3000]) * 0.4
    return amt * g * env(n, 0.01, 0.06)


def rustle(dur, amt=1.0):
    n = int(dur * SR)
    am = filt(np.abs(noise(n)), "lowpass", 18) * 4
    return amt * filt(noise(n), "highpass", 1800) * am * (rng.random(n) > 0.3)


def scrape(dur, amt=1.0, base=180):
    """Stone grinding on stone: stick-slip modulated band noise, distorted."""
    n = int(dur * SR)
    slips = filt((rng.random(n) > 0.9994).astype(float), "lowpass", 30) * 400
    am = np.clip(0.3 + filt(noise(n), "lowpass", 6) * 8 + slips, 0, None)
    x = filt(noise(n), "bandpass", [base, 2400]) * am
    x += 0.6 * filt(noise(n), "bandpass", [base * 0.5, base * 1.2]) * am
    x = np.tanh(x * 1.5)
    fade = np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / (0.04 * SR))
    return amt * x * fade


def clink():
    n = int(1.0 * SR)
    t = np.arange(n) / SR
    out = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d)
              for f, a, d in ((1180, 1, 0.25), (2730, 0.7, 0.15), (4410, 0.5, 0.09), (6190, 0.3, 0.05)))
    c = click()
    return out * 0.5 + np.r_[c, np.zeros(n - len(c))]


def kite_call():
    """Distant black kite: a quavering descending whistle."""
    out = []
    for k, (f0, f1, d) in enumerate(((3100, 2500, 0.55), (2900, 2400, 0.22), (2850, 2350, 0.2), (2800, 2300, 0.2))):
        n = int(d * SR)
        t = np.arange(n) / SR
        f = np.linspace(f0, f1, n) * (1 + 0.03 * np.sin(2 * np.pi * 28 * t))
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
        out += [s * np.sin(np.pi * np.arange(n) / n) ** 1.5, np.zeros(int(0.06 * SR))]
    return np.concatenate(out)


def wind(t0, t1):
    n = int((t1 - t0) * SR)
    t = t0 + np.arange(n) / SR
    g = gust(t)
    rumble = filt(noise(n), "lowpass", 250, 2) * 9 * g ** 2
    buffet = np.tanh(rumble * 1.3)                      # mic diaphragm overloading
    whistle = filt(noise(n), "bandpass", [500, 1600]) * 0.25 * g
    return buffet + whistle


def ir(rt60, dur=None, bright=3000, pre=0.01, seed=1):
    r = np.random.default_rng(seed)
    dur = dur or rt60 * 1.2
    n = int(dur * SR)
    t = np.arange(n) / SR
    h = r.standard_normal(n) * np.exp(-6.9 * t / rt60)
    h = filt(h, "lowpass", bright)
    h[: int(pre * SR)] = 0
    for k in range(6):
        h[int(r.uniform(pre, pre + 0.06) * SR)] += r.uniform(0.3, 0.8)
    return h / np.sqrt((h ** 2).sum())


def load_vo(path):
    with wave.open(path) as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, {2: np.int16, 4: np.int32}[sw]).astype(np.float64)
    x = x.reshape(-1, ch).mean(1) / (2 ** (8 * sw - 1))
    if sr != SR:
        x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x)
    return x


# ---------------------------------------------------------------------------
def build_audio(path):
    bus = {name: np.zeros(N) for name, _, _ in SCENES}
    sec = {name: (a, b) for name, a, b in SCENES}

    # 00:00 office: fan, fluorescent hum, paper, finger on map
    o = bus["office"]
    a, b = sec["office"]
    n = int((b - a) * SR)
    t = np.arange(n) / SR
    o[:n] += filt(noise(n), "bandpass", [200, 1800]) * (0.5 + 0.3 * np.sin(2 * np.pi * 3.1 * 3 * t)) * 0.12
    o[:n] += (np.sin(2 * np.pi * 100 * t) * 0.02 + np.sin(2 * np.pi * 200 * t) * 0.01)
    o[:n] += filt(noise(n), "lowpass", 300) * 0.08
    place(o, thud(60, 0.4, 0.5), 0.02)                     # mic handling as camera settles
    place(o, rustle(1.4, 0.35), 1.85)
    place(o, thud(140, 0.2, 0.3), 3.15)                     # photo laid down
    place(o, rustle(3.6, 0.12), 7.3)                       # finger dragging on the map
    for k in range(5):
        place(o, filt(noise(int(0.3 * SR)), "bandpass", [400, 1500]) * env(int(0.3 * SR), 0.05, 0.08) * 0.05,
              rng.uniform(0.5, 11))                        # chair creaks / shuffles

    # 00:12 hills: wind buffeting, gravel steps, equipment knocks, a kite
    h = bus["hills"]
    a, b = sec["hills"]
    place(h, wind(a, b) * 0.35, a)
    for i in range(5):
        tt = a + 0.1 * i
        while tt < a + 7.0 + 0.15 * i:
            place(h, crunch(rng.uniform(0.4, 1.0) / (1 + 0.5 * i)), tt)
            tt += rng.uniform(0.45, 0.6)
    tt = a
    while tt < a + 7.0:                                    # the operator's own footsteps, loud and close
        place(h, crunch(1.6), tt)
        tt += rng.uniform(0.5, 0.56)
    for k in range(9):
        place(h, thud(rng.uniform(160, 260), 0.15, 0.25) + 0, a + rng.uniform(0.2, 6.8))
    for k in range(7):                                     # stumble: loose stone skitter
        place(h, clack(rng.uniform(1.0, 1.6), 0.4), a + 2.7 + rng.uniform(0, 0.8))
    place(h, kite_call() * 0.05, a + 9.5)

    # 00:25 temple antechamber
    tp = bus["temple"]
    a, b = sec["temple"]
    n = int((b - a) * SR)
    place(tp, filt(wind(a, b), "lowpass", 140) * 0.10, a)
    place(tp, click() * 0.5, a + 0.55)                     # torch switch
    for k in range(6):
        place(tp, crunch(0.6), a + 1.0 + k * 0.7 + rng.uniform(0, 0.15))
    for k in range(40):                                    # trickling grit
        place(tp, clack(rng.uniform(2, 3.5), 0.03), a + rng.uniform(0, 14))
    tt = a + 6.0
    while tt < b - 0.3:                                    # brushing the jamb
        m = int(0.32 * SR)
        place(tp, filt(noise(m), "bandpass", [2000, 7000]) * np.sin(np.pi * np.arange(m) / m) ** 2 * 0.12, tt)
        tt += 1 / 1.6

    # 00:39 opening
    op = bus["opening"]
    a, b = sec["opening"]
    for k, t0 in enumerate((0.3, 0.85, 1.4, 1.95)):
        place(op, clack(rng.uniform(0.6, 0.9), 0.5), a + t0)
        place(op, clack(rng.uniform(0.7, 1.0), 0.35), a + t0 + 0.55)
        place(op, crunch(0.5), a + t0 + 0.05)
    place(op, clink() * 0.35, a + 3.6)
    place(op, scrape(0.35, 0.35, 400), a + 3.65)
    place(op, scrape(4.1, 0.9), a + 5.6)                   # the long grind
    place(op, scrape(1.2, 0.6, 120), a + 8.6)
    place(op, thud(55, 1.2, 1.2), a + 9.55)                # door drops into place inward
    m = int(2.2 * SR)
    place(op, filt(noise(m), "bandpass", [80, 700]) * np.sin(np.pi * np.arange(m) / m) ** 1.5 * 0.35,
          a + 9.6)                                         # air sighing out of the chamber
    for k in range(10):
        place(op, clack(rng.uniform(0.8, 1.3), 0.2), a + 9.6 + rng.uniform(0, 1.5))

    # 00:51 inner chamber
    ch = bus["chamber"]
    a, b = sec["chamber"]
    n = int((b - a) * SR)
    place(ch, filt(noise(n), "lowpass", 70) * 0.25, a)
    for k in range(6):
        place(ch, crunch(0.45), a + 0.4 + 0.55 * k + rng.uniform(0, 0.1))
    scuff_t = a + 5.2
    sc = scrape(0.28, 0.55, 300) + np.r_[clack(1.3, 0.3), np.zeros(int(0.28 * SR) - int(0.25 * SR))]

    # dialogue, if provided
    vodir = os.path.join(HERE, "vo")
    for (t0, _t1, _d, _e, vid) in SUBTITLES:
        p = os.path.join(vodir, vid + ".wav")
        if os.path.exists(p):
            name = next(nm for nm, s0, s1 in SCENES if s0 <= t0 < s1)
            place(bus[name], load_vo(p) * 0.8, t0)

    # Room acoustics per location, then hard cuts between them
    rooms = {"office": (0.45, 0.12), "hills": (None, 0), "temple": (1.6, 0.35),
             "opening": (1.9, 0.35), "chamber": (4.5, 0.5)}
    mix = np.zeros(N)
    for name, s0, s1 in SCENES:
        x = bus[name]
        rt, wet = rooms[name]
        if rt:
            x = x * (1 - wet) + fftconvolve(x, ir(rt, seed=len(name)))[:N] * wet * 3
        gate = np.zeros(N)
        i0, i1 = int(s0 * SR), int(s1 * SR)
        gate[i0:i1] = 1
        f = int(0.004 * SR)
        gate[i0:i0 + f] = np.linspace(0, 1, f)
        gate[i1 - f:i1] = np.linspace(1, 0, f)
        mix += x * gate

    # The echo: the scuff comes back from somewhere far inside, seconds later
    echo = fftconvolve(filt(sc, "lowpass", 1400), ir(3.0, 3.5, 1200, pre=0.0, seed=99))[: int(3.0 * SR)]
    echo *= np.minimum(1, np.arange(len(echo)) / (0.35 * SR))
    place(mix, sc * 0.8 + fftconvolve(sc, ir(0.9, seed=7))[: len(sc)] * 0.6, scuff_t)
    place(mix, echo * 0.30, scuff_t + 2.6)

    # Camcorder mic: preamp hiss, AGC pumping, soft clipping, narrow band
    mix += filt(noise(N), "highpass", 3000) * 0.004
    e = np.abs(mix)
    e = sosfilt(butter(1, 3, "lowpass", fs=SR, output="sos"), e)
    agc = np.clip(0.18 / (e + 1e-3), 0.3, 5.0)
    agc = sosfilt(butter(1, 1.2, "lowpass", fs=SR, output="sos"), agc)
    mix = np.tanh(mix * agc * 1.2)
    mix = filt(filt(mix, "highpass", 110), "lowpass", 9000)
    mix += filt(noise(N), "highpass", 4000) * 0.006           # tape hiss
    mix += np.sin(2 * np.pi * 50 * np.arange(N) / SR) * 0.002

    i = int(CUT_TO_BLACK * SR)
    mix[i:] = 0                                               # cut to black: dead silence
    mix /= np.abs(mix).max() / 0.89
    pcm = (mix * 32767).astype(np.int16)
    st = np.stack([pcm, pcm], 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())


if __name__ == "__main__":
    build_audio(os.path.join(HERE, "out", "soundtrack.wav"))
