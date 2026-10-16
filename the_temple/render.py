#!/usr/bin/env python3
"""EPISODE 01 - THE TEMPLE: procedural 60 s concept video in a 1987 camcorder look.

    python render.py                      # full video -> out/the_temple_ep01.mp4
    python render.py --stills 3 14 30 45 55   # preview frames -> out/still_*.png
"""
import argparse
import os
import subprocess
import sys
from multiprocessing import Pool

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import (CUT_TO_BLACK, FONTS, FPS, H, HERE, NFRAMES, OH, OW, SCENES, SUBTITLES, W, kf)

_scenes = {}


def scene_at(t):
    for name, a, b in SCENES:
        if a <= t < b:
            return name, t - a
    return None, 0.0


def get_scene(name):
    if name not in _scenes:
        from scenes import SCENE_CLASSES
        _scenes[name] = SCENE_CLASSES[name]()
    return _scenes[name]


# ---------------------------------------------------------------------------
# Camcorder / VHS degradation
# ---------------------------------------------------------------------------
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_vig = (1 - 0.30 * (((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2))[..., None]
_stamp_font = ImageFont.truetype(f"{FONTS}/VT323.woff", 24)


def burn_stamp(img, text):
    pil = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(pil)
    for i, line in enumerate(("OCT 14 1987", text)):
        d.text((W - 136, H - 62 + 21 * i), line, font=_stamp_font, fill=255)
    a = np.asarray(pil, np.float32)[..., None] / 255
    sh = np.roll(a, (2, 2), (0, 1))
    img = img * (1 - 0.6 * sh)
    return img * (1 - a) + a * np.array([1.0, 0.95, 0.75], np.float32) * 1.05


def camcorder(img, fi, gain, blur, stamp, glitch=0.0):
    rng = np.random.default_rng(9000 + fi)
    x = np.maximum(img * gain, 0)
    if blur > 0.25:
        x = cv2.GaussianBlur(x, (0, 0), blur)
    x = cv2.GaussianBlur(x, (0, 0), 0.7)
    hi = np.clip(x - 0.85, 0, None)
    x = x + cv2.GaussianBlur(hi, (0, 0), 7) * 0.9
    x = np.clip(x, 0, 1.0)
    if stamp:
        x = burn_stamp(x, stamp)

    Y = x @ np.array([0.299, 0.587, 0.114], np.float32)
    C = x - Y[..., None]
    C = cv2.blur(C, (13, 1))
    C = np.roll(C, 4, axis=1) * 0.85
    lvl = 0.016 + 0.018 * max(0.0, gain - 1.0)
    cn = rng.normal(0, 1, (H, W // 24, 2)).astype(np.float32)
    cn = cv2.resize(cn, (W, H), interpolation=cv2.INTER_LINEAR) * lvl * 1.2
    C[..., 0] += cn[..., 0]
    C[..., 2] += cn[..., 1]

    Yb = cv2.GaussianBlur(Y, (0, 0), 1.6)
    Y = Y + 0.6 * (Y - Yb)
    grain = rng.normal(0, 1, (H, W)).astype(np.float32)
    grain = cv2.blur(grain, (3, 1)) * lvl * 1.8
    Y = Y + grain * (0.5 + 0.8 * np.sqrt(np.clip(1 - Y, 0, 1)))
    out = Y[..., None] + C

    jit = rng.normal(0, 0.18, H) + 0.6 * np.sin(np.arange(H) * 0.031 + fi * 0.9) * 0.4
    jit[H - 7:] += 14 + rng.normal(0, 3, 7)
    if glitch > 0:
        band = rng.integers(0, H - 60)
        jit[band:band + 60] += rng.normal(0, 25 * glitch, 60)
        jit += rng.normal(0, 3 * glitch, H)
    mx = (_xx + jit[:, None].astype(np.float32))
    my = _yy + (glitch * 30 * rng.random() if glitch > 0.5 else 0)
    out = cv2.remap(out, mx, my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    if glitch > 0:
        out += (rng.random((H, 1)) > 1 - 0.25 * glitch) * rng.random((H, W)).astype(np.float32)[..., None] * 0.6
    if rng.random() < 0.08:  # tape dropout
        y0, x0 = rng.integers(0, H), rng.integers(0, W - 80)
        out[y0, x0:x0 + rng.integers(20, 80)] = 0.9

    out = out * _vig
    out = 0.035 + out * 0.95
    out *= np.array([1.0, 1.01, 0.96], np.float32)
    return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------
# Subtitles (post-production, crisp)
# ---------------------------------------------------------------------------
_sub_cache = {}


def subtitle_layer(idx):
    if idx in _sub_cache:
        return _sub_cache[idx]
    _, _, dev, eng, _ = SUBTITLES[idx]
    f_dev = ImageFont.truetype(f"{FONTS}/NotoSansDevanagari.ttf", 34, layout_engine=ImageFont.Layout.RAQM)
    f_eng = ImageFont.truetype(f"{FONTS}/RobotoCondensed-Italic.woff", 26)
    pil = Image.new("RGBA", (OW, OH), (0, 0, 0, 0))
    d = ImageDraw.Draw(pil)
    for text, font, y in ((dev, f_dev, OH - 190), (eng, f_eng, OH - 138)):
        w = d.textlength(text, font=font)
        d.text(((OW - w) / 2, y), text, font=font, fill=(255, 255, 250, 255),
               stroke_width=3, stroke_fill=(0, 0, 0, 200))
    arr = np.asarray(pil, np.float32) / 255
    _sub_cache[idx] = arr
    return arr


def overlay_subtitles(frame, t):
    for i, (a, b, *_rest) in enumerate(SUBTITLES):
        if a <= t < b:
            k = min(1.0, (t - a) / 0.12, (b - t) / 0.12)
            lay = subtitle_layer(i)
            al = lay[..., 3:4] * k
            frame = frame * (1 - al) + lay[..., :3] * al
    return frame


# ---------------------------------------------------------------------------
def render_frame(fi):
    t = fi / FPS
    if t >= CUT_TO_BLACK:
        return np.zeros((OH, OW, 3), np.uint8).tobytes()
    name, lt = scene_at(t)
    img, gain, blur, stamp = get_scene(name).frame(lt)
    glitch = 0.0
    if name != "office" and lt < 0.12:
        glitch = 1 - lt / 0.12
    out = camcorder(img, fi, gain, blur, stamp, glitch)
    out = cv2.resize(out, (OW, OH), interpolation=cv2.INTER_LINEAR)
    out = overlay_subtitles(out, t)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", type=float, nargs="*", help="render preview stills at these seconds")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "the_temple_ep01.mp4"))
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    if args.stills:
        for s in args.stills:
            buf = render_frame(int(round(s * FPS)))
            img = np.frombuffer(buf, np.uint8).reshape(OH, OW, 3)
            p = os.path.join(os.path.dirname(args.out), f"still_{s:05.2f}.png")
            Image.fromarray(img).save(p)
            print(p)
        return

    from audio import build_audio
    wav = os.path.join(os.path.dirname(args.out), "soundtrack.wav")
    build_audio(wav)
    print("audio ->", wav)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{OW}x{OH}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(args.workers) as pool:
        for i, buf in enumerate(pool.imap(render_frame, range(NFRAMES), chunksize=4)):
            ff.stdin.write(buf)
            if i % 50 == 0:
                print(f"frame {i}/{NFRAMES}", file=sys.stderr, flush=True)
    ff.stdin.close()
    ff.wait()
    print("video ->", args.out)


if __name__ == "__main__":
    main()
