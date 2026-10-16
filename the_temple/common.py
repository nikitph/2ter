"""Shared constants, timing helpers, procedural noise and drawing helpers."""
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

FPS = 25                      # PAL camcorder
DUR = 60.0
NFRAMES = int(FPS * DUR)
W, H = 640, 480               # internal "tape" resolution (4:3)
OW, OH = 960, 720             # delivered resolution

# Scene boundaries (global seconds). The last 0.4 s is the cut to black.
SCENES = [
    ("office", 0.0, 12.0),
    ("hills", 12.0, 25.0),
    ("temple", 25.0, 39.0),
    ("opening", 39.0, 51.0),
    ("chamber", 51.0, 59.6),
]
CUT_TO_BLACK = 59.6

# (start, end, sanskrit, english, vo-id)
SUBTITLES = [
    (1.0, 5.9, "स्थानीयेन आदिवासिना प्राचीनस्य देवालयस्य स्थानं निवेदितम्।",
     "A local Adivasi man has reported the location of an ancient temple.", "officer_1"),
    (6.6, 11.6, "स्थलस्य सर्वेक्षणं चित्राङ्कनं च कुर्वन्तु।",
     "Survey and film the site.", "officer_2"),
    (19.4, 21.6, "अत्र।", "Here.", "guide_1"),
    (33.4, 37.6, "अन्तः किमपि स्थानमस्ति।", "There is a space beyond.", "researcher_1"),
    (44.0, 46.0, "शनैः।", "Slowly.", "leader_1"),
]


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def ramp(t, a, b):
    return float(smooth((t - a) / (b - a)))


def kf(t, keys):
    """Smoothstep interpolation through (time, value) keyframes."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = float(smooth((t - t0) / (t1 - t0))) if t1 > t0 else 1.0
            return v0 + (v1 - v0) * u
    return keys[-1][1]


def gust(t):
    """Wind-gust envelope shared by picture (shake) and sound (mic buffeting)."""
    t = np.asarray(t, dtype=np.float64)
    g = (0.55 + 0.25 * np.sin(2 * np.pi * 0.21 * t + 1.0)
         + 0.18 * np.sin(2 * np.pi * 0.53 * t + 2.3)
         + 0.12 * np.sin(2 * np.pi * 1.37 * t + 0.4))
    return np.clip(g, 0.05, 1.2)


def fbm(h, w, scale, octaves=5, seed=0):
    """Fractal value noise in [0,1]-ish, shape (h, w)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot, s = 1.0, 0.0, float(scale)
    for _ in range(octaves):
        if s < 1:
            break
        gh, gw = int(h / s) + 3, int(w / s) + 3
        g = rng.random((gh, gw)).astype(np.float32)
        up = cv2.resize(g, (int(gw * s), int(gh * s)), interpolation=cv2.INTER_CUBIC)
        out += amp * up[:h, :w]
        tot += amp
        amp *= 0.5
        s /= 2
    out /= tot
    lo, hi = np.percentile(out, 1), np.percentile(out, 99)
    return np.clip((out - lo) / (hi - lo + 1e-6), 0, 1)


def fbm1(n, scale, seed):
    return fbm(4, n, scale, 5, seed)[1]


class Shake:
    """Smooth pseudo-random handheld motion; returns (dx, dy, rot) in [-1, 1]."""

    def __init__(self, seed, n=6, fmin=0.2, fmax=2.2):
        r = np.random.default_rng(seed)
        self.f = r.uniform(fmin, fmax, (3, n))
        self.p = r.uniform(0, 2 * np.pi, (3, n))
        self.a = 1.0 / (1 + np.arange(n))

    def __call__(self, t):
        v = (np.sin(2 * np.pi * self.f * t + self.p) * self.a).sum(1) / self.a.sum() * 1.8
        return v


def view(canvas, cx, cy, zoom, rot=0.0):
    """Camera: map canvas point (cx, cy) to frame centre, scaled by zoom."""
    M = cv2.getRotationMatrix2D((float(cx), float(cy)), float(rot), float(zoom))
    M[0, 2] += W / 2 - cx
    M[1, 2] += H / 2 - cy
    return cv2.warpAffine(canvas, M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT)


def P(x, y):
    return (int(round(x)), int(round(y)))


def paint(img, color, draw, blur=0.0):
    """Draw a shape into a mask (anti-aliased) and composite `color` through it."""
    m = np.zeros(img.shape[:2], np.uint8)
    draw(m)
    a = m.astype(np.float32) / 255.0
    if blur:
        a = cv2.GaussianBlur(a, (0, 0), blur)
    a = a[..., None]
    img *= 1 - a
    img += a * np.asarray(color, np.float32)
    return a


def paste(canvas, patch, alpha, M):
    """Affine-warp an RGB patch + alpha onto a canvas."""
    ch, cw = canvas.shape[:2]
    p = cv2.warpAffine(patch, M, (cw, ch), flags=cv2.INTER_LINEAR)
    a = cv2.warpAffine(alpha, M, (cw, ch), flags=cv2.INTER_LINEAR)[..., None]
    canvas *= 1 - a
    canvas += p * a
    return a


_sprites = {}


def stone_sprite(rx, ry, seed, base):
    """Irregular, lit, textured stone (RGB patch + alpha), cached."""
    key = (int(rx), int(ry), seed, tuple(np.round(base, 3)))
    if key in _sprites:
        return _sprites[key]
    r = np.random.default_rng(seed)
    w, h = int(rx * 2 + 8), int(ry * 2 + 8)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = (xx - w / 2) / rx, (yy - h / 2) / ry
    ang, rad = np.arctan2(ny, nx), np.hypot(nx, ny)
    pert = 1 + sum(r.uniform(0.03, 0.09) * np.sin(k * ang + r.uniform(0, 6.28)) for k in range(2, 6))
    q = rad / pert
    alpha = smooth((1 - q) / (2.0 / max(rx, 2)))
    nz = np.sqrt(np.clip(1 - q * q, 0, 1))
    lam = np.clip(-0.45 * nx / pert - 0.65 * ny / pert + 0.6 * nz, 0, 1)
    tex = fbm(h, w, max(2, rx / 2.5), 3, seed)
    col = np.asarray(base, np.float32) * ((0.18 + 0.9 * lam) * (0.7 + 0.55 * tex))[..., None]
    _sprites[key] = (col.astype(np.float32), alpha.astype(np.float32))
    return _sprites[key]


def blit(img, patch, alpha, cx, cy):
    ph, pw = alpha.shape
    x0, y0 = int(round(cx - pw / 2)), int(round(cy - ph / 2))
    ih, iw = img.shape[:2]
    a0, b0 = max(0, -x0), max(0, -y0)
    a1, b1 = min(pw, iw - x0), min(ph, ih - y0)
    if a1 <= a0 or b1 <= b0:
        return
    a = alpha[b0:b1, a0:a1, None]
    reg = img[y0 + b0:y0 + b1, x0 + a0:x0 + a1]
    reg *= 1 - a
    reg += patch[b0:b1, a0:a1] * a


def stone(img, cx, cy, rx, ry, ang, base, seed=None):
    """A rubble stone with a contact shadow."""
    if seed is None:
        seed = int(abs(cx * 7.3 + cy * 13.1 + rx * 3.7)) % 100000
    rx, ry = max(2, rx), max(2, ry)
    patch, alpha = stone_sprite(rx, ry, seed, base)
    blit(img, np.zeros_like(patch), alpha * 0.7, cx + rx * 0.15, cy + ry * 0.3)
    blit(img, patch, alpha, cx, cy)


def bush(img, x, y, s, r):
    """Dry scrub: a cluster of small dark-olive blobs."""
    for _ in range(int(6 + s * 0.8)):
        ox, oy = r.normal(0, s * 0.7), r.normal(0, s * 0.3) - s * 0.2
        c = r.uniform(0.75, 1.25)
        cv2.circle(img, P(x + ox, y + oy), max(1, int(s * r.uniform(0.2, 0.45))),
                   (0.20 * c, 0.21 * c, 0.12 * c), -1)
    for _ in range(int(2 + s * 0.3)):
        ox, oy = r.normal(0, s * 0.5), r.normal(0, s * 0.2) - s * 0.4
        cv2.circle(img, P(x + ox, y + oy), max(1, int(s * 0.15)), (0.38, 0.36, 0.22), -1)
