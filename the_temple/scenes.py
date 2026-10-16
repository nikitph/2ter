"""The five shots. Each scene's frame(t) takes local seconds and returns
(image HxWx3 float, exposure gain, focus blur in px, stamp time string)."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import (FONTS, H, W, P, Shake, bush, fbm, fbm1, gust, kf, paint, paste,
                    ramp, smooth, stone, view)


def _rng(seed):
    return np.random.default_rng(seed)


def _font(name, size):
    return ImageFont.truetype(f"{FONTS}/{name}", size, layout_engine=ImageFont.Layout.RAQM)


# ---------------------------------------------------------------------------
# 00:00-00:12  EXPEDITION BRIEFING
# ---------------------------------------------------------------------------
class Office:
    CW, CH = 1000, 750

    def __init__(self):
        cw, ch = self.CW, self.CH
        img = np.empty((ch, cw, 3), np.float32)
        st = fbm(ch, cw, 140, 5, 11)
        img[:] = np.array([0.50, 0.56, 0.48], np.float32) * (0.72 + 0.5 * st[..., None])
        img[285:330] *= 0.78

        # Calendar on the wall
        img[95:235, 120:225] = (0.80, 0.78, 0.72)
        img[95:122, 120:225] = (0.55, 0.12, 0.10)
        for gy in range(132, 230, 16):
            img[gy, 128:218] = (0.45, 0.45, 0.42)
        for gx in range(128, 222, 13):
            img[128:228, gx] = (0.52, 0.52, 0.48)

        # Window, blown out behind the officer
        wx0, wx1, wy0, wy1 = 330, 670, 40, 300
        hh, ww = wy1 - wy0, wx1 - wx0
        trees = fbm(hh, ww, 40, 4, 13)
        lum = 1.7 - 0.55 * smooth((trees - 0.55) / 0.2)
        win = np.stack([lum * 0.95, lum, lum * 0.9], -1)
        img[wy0:wy1, wx0:wx1] = win
        for bx in range(wx0 + 24, wx1 - 10, 40):
            img[wy0:wy1, bx:bx + 5] = (0.14, 0.13, 0.12)
        img[wy0 + 120:wy0 + 128, wx0:wx1] = (0.25, 0.22, 0.18)
        for (a, b) in ((wy0 - 10, wy0), (wy1, wy1 + 10)):
            img[a:b, wx0 - 10:wx1 + 10] = (0.30, 0.26, 0.20)
        img[wy0:wy1, wx0 - 10:wx0] = (0.30, 0.26, 0.20)
        img[wy0:wy1, wx1:wx1 + 10] = (0.30, 0.26, 0.20)

        # Steel cupboard
        cx0, cx1, cy0, cy1 = 785, 985, 30, 430
        dent = fbm(cy1 - cy0, cx1 - cx0, 30, 4, 14)
        img[cy0:cy1, cx0:cx1] = np.array([0.40, 0.45, 0.48]) * (0.85 + 0.25 * dent[..., None])
        img[cy0:cy1, cx0:cx0 + 6] *= 1.35
        img[cy0:cy1, 883:887] = (0.10, 0.11, 0.12)
        img[200:250, 870:878] = (0.75, 0.75, 0.72)
        img[200:250, 892:900] = (0.75, 0.75, 0.72)
        for vy in range(60, 130, 9):
            img[vy:vy + 3, 815:860] = (0.20, 0.22, 0.24)

        # Officer: backlit by the window, so mostly silhouette with a rim
        body = np.zeros((ch, cw), np.uint8)
        cv2.ellipse(body, (500, 150), (42, 54), 0, 0, 360, 255, -1, cv2.LINE_AA)
        cv2.rectangle(body, (478, 190), (522, 240), 255, -1)
        cv2.fillPoly(body, [np.array([(360, 340), (372, 262), (420, 232), (580, 232), (628, 262),
                                      (640, 340)], np.int32)], 255, cv2.LINE_AA)
        bm = body.astype(np.float32)[..., None] / 255
        shirt = np.array([0.30, 0.26, 0.17], np.float32)
        tone = np.full((ch, cw, 3), shirt)
        tone[:205] = (0.13, 0.10, 0.08)                 # head
        tone[90:122] = (0.07, 0.06, 0.05)               # hair
        img = img * (1 - bm) + tone * bm
        img[244:252, 400:445] = (0.20, 0.17, 0.11)      # epaulettes
        img[244:252, 555:600] = (0.20, 0.17, 0.11)
        img[285:315, 430:470] *= 0.8                    # pocket
        img[285:315, 530:570] *= 0.8
        img[283:286, 435:438] = (0.8, 0.7, 0.4)         # badge glint
        er = cv2.erode(body, np.ones((7, 7), np.uint8))
        rim = cv2.GaussianBlur((body.astype(np.float32) - er) / 255, (0, 0), 2.5)[..., None]
        img += rim * np.array([0.9, 0.85, 0.7]) * 0.9

        # Desk
        grain = cv2.resize(fbm(ch, cw // 10, 6, 4, 15), (cw, ch))
        wood = np.array([0.30, 0.18, 0.10]) * (0.65 + 0.55 * grain[..., None])
        img[330:] = wood[330:]
        img[330:337] = (0.45, 0.32, 0.20)

        # Files with red tape, rotary phone, tea glass
        cv2.rectangle(img, (20, 400), (175, 560), (0.70, 0.60, 0.40), -1)
        for k in range(5):
            cv2.line(img, (20, 400 + 30 * k), (175, 402 + 30 * k), (0.50, 0.40, 0.25), 2)
        cv2.rectangle(img, (85, 398), (97, 562), (0.55, 0.10, 0.08), -1)
        cv2.ellipse(img, (900, 520), (70, 45), 0, 0, 360, (0.05, 0.05, 0.05), -1, cv2.LINE_AA)
        cv2.circle(img, (900, 520), 28, (0.20, 0.20, 0.20), -1, cv2.LINE_AA)
        cv2.circle(img, (900, 520), 9, (0.65, 0.62, 0.55), -1, cv2.LINE_AA)
        cv2.rectangle(img, (850, 465), (950, 482), (0.08, 0.08, 0.08), -1)
        cv2.ellipse(img, (870, 410), (22, 10), 0, 0, 360, (0.40, 0.25, 0.12), -1, cv2.LINE_AA)
        cv2.ellipse(img, (870, 410), (22, 10), 0, 0, 360, (0.85, 0.85, 0.8), 2, cv2.LINE_AA)

        # Survey map in perspective on the desk
        mp, route = self._make_map()
        mh, mw = mp.shape[:2]
        quad = np.float32([(165, 350), (795, 345), (850, 735), (110, 745)])
        Hm = cv2.getPerspectiveTransform(np.float32([(0, 0), (mw, 0), (mw, mh), (0, mh)]), quad)
        warped = cv2.warpPerspective(mp, Hm, (cw, ch))
        ma = cv2.warpPerspective(np.ones((mh, mw), np.float32), Hm, (cw, ch))
        sh = np.roll(cv2.GaussianBlur(ma, (0, 0), 8), (8, 6), (0, 1))
        img *= (1 - 0.45 * sh)[..., None]
        img = img * (1 - ma[..., None]) + warped * ma[..., None]
        pts = cv2.perspectiveTransform(np.float32(route)[None], Hm)[0]
        self.route = pts

        # Gentle light falloff from the tube light / window
        yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
        fall = 1.0 - 0.35 * (((xx - 520) / 700) ** 2 + ((yy - 330) / 600) ** 2)
        img[330:] *= fall[330:, :, None]
        self.base = img.astype(np.float32)
        self.photo, self.photo_a = self._make_photo()
        self.shake = Shake(101)

    @staticmethod
    def _make_map():
        mw, mh = 720, 420
        paper = 0.92 + 0.12 * fbm(mh, mw, 80, 4, 16)
        img = np.stack([paper * 0.88, paper * 0.83, paper * 0.68], -1).astype(np.float32)
        field = fbm(mh, mw, 120, 4, 17)
        fr = np.abs(((field * 16) % 1.0) - 0.5)
        line = smooth((fr - 0.44) / 0.06)
        idx = np.floor(field * 16).astype(int) % 5 == 0
        img *= (1 - (0.25 + 0.2 * idx)[..., None] * line[..., None] * np.array([0.3, 0.55, 0.8]))
        for gx in range(0, mw, 90):
            img[:, gx:gx + 1] *= (0.80, 0.85, 0.95)
        for gy in range(0, mh, 90):
            img[gy:gy + 1, :] *= (0.80, 0.85, 0.95)
        xs = np.arange(mw)
        ry = (300 - 0.18 * xs + 28 * np.sin(xs / 55.0) + 12 * np.sin(xs / 17.0)).astype(int)
        for x, y in zip(xs, ry):
            img[max(0, y - 1):y + 2, x] = (0.35, 0.45, 0.58)
        for x in range(0, mw, 14):
            y = int(110 + 0.25 * x + 18 * math.sin(x / 70))
            cv2.line(img, (x, y), (x + 7, int(110 + 0.25 * (x + 7) + 18 * math.sin((x + 7) / 70))),
                     (0.15, 0.12, 0.10), 2)
        # folds
        for fx in (mw // 3, 2 * mw // 3):
            img[:, fx - 3:fx + 3] *= 0.88
            img[:, fx + 3:fx + 5] *= 1.06
        img[mh // 2 - 2:mh // 2 + 2] *= 0.88
        # print
        pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
        d = ImageDraw.Draw(pil)
        f_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        f_dev = _font("NotoSansDevanagari.ttf", 15)
        d.text((14, 8), "SURVEY OF INDIA    SHEET No. 64 C/9    1 : 50,000", fill=(40, 30, 25), font=f_small)
        d.text((150, 330), "देवगढ़", fill=(40, 30, 25), font=f_dev)
        d.text((470, 120), "बाघ डोंगरी", fill=(40, 30, 25), font=f_dev)
        d.text((560, 380), "R. Kanhar", fill=(50, 60, 80), font=f_small)
        for (x, y) in ((140, 352), (150, 365), (163, 358), (158, 372)):
            d.rectangle((x, y, x + 4, y + 4), fill=(30, 25, 20))
        img = np.asarray(pil).astype(np.float32) / 255
        # Faint pencil route the officer traces
        route = [(160, 345), (210, 300), (255, 285), (300, 240), (350, 228), (395, 190),
                 (430, 160), (470, 150), (505, 118)]
        rr = np.array(route, np.float64)
        for (a, b) in zip(rr, rr[1:]):
            n = int(np.hypot(*(b - a)) / 6)
            for k in range(0, n, 2):
                p0 = a + (b - a) * k / n
                p1 = a + (b - a) * (k + 1) / n
                cv2.line(img, P(*p0), P(*p1), (0.55, 0.20, 0.18), 2)
        cv2.circle(img, P(*route[-1]), 9, (0.55, 0.20, 0.18), 2)
        return img, route

    @staticmethod
    def _make_photo():
        ph, pw = 230, 310
        g = 0.45 + 0.35 * fbm(ph, pw, 26, 5, 21)
        leaves = fbm(ph, pw, 7, 3, 22)
        g = g * (0.7 + 0.5 * leaves)
        g[:60] = g[:60] * 0.6 + 0.45
        # stone entrance
        g[60:85, 150:268] = 0.78 - 0.15 * leaves[60:85, 150:268]
        for x in range(158, 262, 12):
            g[66:79, x:x + 5] *= 0.6
        g[85:215, 158:178] = 0.70 - 0.2 * leaves[85:215, 158:178]
        g[85:215, 240:260] = 0.70 - 0.2 * leaves[85:215, 240:260]
        g[85:215, 178:240] = 0.08 + 0.05 * leaves[85:215, 178:240]
        g[180:230, 140:280] = g[180:230, 140:280] * 0.5 + 0.3 * leaves[180:230, 140:280]
        # the informant: dark torso, white dhoti
        cv2.circle(g, (108, 92), 10, 0.15, -1, cv2.LINE_AA)
        cv2.rectangle(g, (104, 100), (112, 106), 0.18, -1)
        cv2.ellipse(g, (108, 126), (13, 22), 0, 0, 360, 0.22, -1, cv2.LINE_AA)
        cv2.fillPoly(g, [np.array([(94, 142), (122, 142), (126, 192), (90, 192)], np.int32)], 0.88)
        cv2.line(g, (100, 192), (100, 214), 0.15, 5)
        cv2.line(g, (116, 192), (117, 214), 0.15, 5)
        cv2.line(g, (96, 112), (88, 150), 0.2, 5)
        cv2.line(g, (120, 112), (140, 120), 0.2, 5)
        g = cv2.GaussianBlur(g, (0, 0), 0.9)
        g += _rng(23).normal(0, 0.035, g.shape).astype(np.float32)
        yy, xx = np.mgrid[0:ph, 0:pw]
        g *= 1 - 0.35 * (((xx - pw / 2) / pw) ** 2 + ((yy - ph / 2) / ph) ** 2)
        rgb = np.stack([g * 1.0, g * 0.95, g * 0.85], -1)
        b = 16
        out = np.full((ph + 2 * b, pw + 2 * b, 3), (0.93, 0.92, 0.88), np.float32)
        out[b:b + ph, b:b + pw] = rgb
        return out.astype(np.float32), np.ones(out.shape[:2], np.float32)

    def _arm(self, img, wrist, finger=None):
        shoulder = np.array([590.0, 255.0])
        wrist = np.asarray(wrist, np.float64)
        elbow = shoulder + (wrist - shoulder) * 0.5 + np.array([45.0, 25.0])
        cuff = wrist + (elbow - wrist) * 0.25
        cv2.line(img, P(*shoulder), P(*elbow), (0.36, 0.31, 0.20), 52)
        cv2.line(img, P(*elbow), P(*cuff), (0.40, 0.34, 0.22), 42)
        cv2.line(img, P(*(shoulder + [-6, -8])), P(*(elbow + [-6, -8])), (0.50, 0.43, 0.28), 18)
        cv2.line(img, P(*(elbow + [-5, -7])), P(*(cuff + [-5, -7])), (0.54, 0.46, 0.30), 14)
        cv2.line(img, P(*cuff), P(*wrist), (0.40, 0.26, 0.16), 30)
        ang = math.degrees(math.atan2(*(wrist - elbow)[::-1]))
        cv2.ellipse(img, P(*wrist), (26, 20), ang, 0, 360, (0.42, 0.27, 0.17), -1)
        if finger is not None:
            cv2.line(img, P(*wrist), P(*finger), (0.44, 0.29, 0.18), 10)
            cv2.circle(img, P(*finger), 5, (0.50, 0.35, 0.24), -1)

    def frame(self, t):
        img = self.base.copy()

        # Ceiling fan, silhouetted against the window
        ang = t * 2 * np.pi * 3.1
        a = paint(img, (0.10, 0.09, 0.08), lambda m: cv2.ellipse(m, (500, 34), (250, 16), 0, 0, 360, 90, -1))
        for k in range(3):
            th = ang + k * 2 * np.pi / 3
            tip = (500 + 245 * math.cos(th), 34 + 14 * math.sin(th))
            cv2.line(img, (500, 34), P(*tip), (0.10, 0.09, 0.08), 9)
        cv2.line(img, (500, 0), (500, 30), (0.12, 0.11, 0.10), 6)
        cv2.ellipse(img, (500, 34), (24, 12), 0, 0, 360, (0.16, 0.15, 0.13), -1)

        # Photograph placed on the table
        if t > 1.7:
            u = ramp(t, 1.8, 3.2)
            px, py = 520 + (640 - 520) * u, 300 + (520 - 300) * u
            rot = -18 + 21 * u
            sc = 0.55 + 0.45 * u
            ph, pw = self.photo.shape[:2]
            M = cv2.getRotationMatrix2D((pw / 2, ph / 2), rot, sc)
            M[0, 2] += px - pw / 2
            M[1, 2] += py - ph / 2
            shadow = cv2.warpAffine(self.photo_a, M, (self.CW, self.CH))
            shadow = np.roll(cv2.GaussianBlur(shadow, (0, 0), 5 + 10 * (1 - u)), (int(10 + 30 * (1 - u)), 8), (0, 1))
            img *= (1 - 0.5 * shadow)[..., None]
            paste(img, self.photo, self.photo_a, M)
            if t < 4.3:
                corner = np.array([px + pw * sc * 0.48, py + ph * sc * 0.15])
                back = ramp(t, 3.4, 4.3)
                wrist = corner + (np.array([600.0, 300.0]) - corner) * back
                self._arm(img, wrist)

        # Finger traces the route
        if 6.4 < t < 12.0:
            reach = ramp(t, 6.4, 7.2) * (1 - ramp(t, 11.2, 12.0))
            u = ramp(t, 7.3, 10.9)
            r = self.route
            seg = np.cumsum(np.r_[0, np.hypot(*np.diff(r, axis=0).T)])
            s = u * seg[-1]
            tip = np.array([np.interp(s, seg, r[:, 0]), np.interp(s, seg, r[:, 1])])
            rest = np.array([600.0, 300.0])
            tip = rest + (tip - rest) * reach
            wrist = tip + np.array([70.0, -35.0])
            self._arm(img, wrist, tip)

        # Tube-light flicker through the fan blades
        img *= 1 + 0.025 * math.sin(t * 2 * np.pi * 9.3)

        cx = kf(t, [(0, 500), (3.3, 505), (5.6, 670), (6.4, 670), (8.0, 400), (12, 420)])
        cy = kf(t, [(0, 378), (3.3, 385), (5.6, 505), (6.4, 505), (8.0, 545), (12, 550)])
        zm = kf(t, [(0, 0.69), (0.4, 0.72), (0.8, 0.68), (3.3, 0.74), (5.6, 1.6), (6.4, 1.6), (8.0, 1.2), (12, 1.25)])
        sx, sy, sr = self.shake(t)
        frame = view(img, cx + 4 * sx, cy + 3 * sy, zm, 0.5 * sr)
        blur = kf(t, [(0, 8), (0.5, 3.5), (0.9, 6), (1.5, 1.2), (2.1, 0), (4.6, 0), (5.0, 2.0), (5.6, 0)])
        stamp = "10:42:%02d" % (7 + int(t))
        return frame, 1.0, blur, stamp


# ---------------------------------------------------------------------------
# 00:12-00:25  THE HILLS
# ---------------------------------------------------------------------------
class Hills:
    CW, CH = 1800, 720

    def __init__(self):
        cw, ch = self.CW, self.CH
        yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
        x1 = np.arange(cw, dtype=np.float32)
        img = np.empty((ch, cw, 3), np.float32)
        img[:] = np.array([1.35, 1.32, 1.22]) - (yy / 380)[..., None] * np.array([0.12, 0.10, 0.04])

        far_y = 245 + 70 * fbm1(cw, 260, 31) - 40 * smooth((x1 - 1200) / 600)
        mid_y = 335 + 85 * fbm1(cw, 170, 32) - 150 * smooth((x1 - 1080) / 520)
        near_y = 470 + 40 * fbm1(cw, 120, 33)
        tex1 = fbm(ch, cw, 40, 5, 34)[..., None]
        tex2 = fbm(ch, cw, 10, 3, 35)[..., None]

        far = (yy > far_y[None])[..., None]
        img = np.where(far, np.array([0.88, 0.84, 0.77]) * (0.97 + 0.04 * tex1), img)
        mid = (yy > mid_y[None])[..., None]
        rock = np.array([0.62, 0.50, 0.37]) * (0.68 + 0.45 * tex1) * (0.8 + 0.35 * tex2)
        rock = rock * np.where(tex2 < 0.22, 0.65, 1.0)
        haze = smooth((520 - yy) / 200)[..., None] * 0.25
        rock = rock * (1 - haze) + np.array([0.9, 0.86, 0.78]) * haze
        img = np.where(mid, rock, img)
        near = (yy > near_y[None])[..., None]
        ground = np.array([0.70, 0.58, 0.43]) * (0.7 + 0.45 * tex2) * (0.8 + 0.4 * tex1)
        img = np.where(near, ground, img).astype(np.float32)

        # Dirt track to the jeep, and a footpath up the hill
        def band(pts, w0, w1, col, rough=0.25):
            n = len(pts)
            for k in range(n - 1):
                w = w0 + (w1 - w0) * k / (n - 1)
                cv2.line(img, P(*pts[k]), P(*pts[k + 1]), col, max(2, int(w)))
        tr = [(-50 + 0, 760), (150, 640), (320, 560), (470, 505), (590, 482)]
        band(tr, 190, 40, (0.86, 0.75, 0.58))
        band([(a + 0, b) for a, b in tr], 6, 2, (0.62, 0.52, 0.40))
        fp = [(610, 485), (760, 720)]
        cv2.line(img, (600, 488), (690, 560), (0.82, 0.71, 0.55), 26)
        bez = lambda u: ((1 - u) ** 2 * np.array([700, 760]) + 2 * u * (1 - u) * np.array([1060, 540])
                         + u * u * np.array([1330, 410]))
        self.path = bez
        pts = [bez(u) for u in np.linspace(0, 1, 40)]
        for k in range(39):
            cv2.line(img, P(*pts[k]), P(*pts[k + 1]), (0.80, 0.69, 0.53), max(3, int(70 * (1 - k / 39) + 6)))
        img *= (0.85 + 0.25 * tex2)

        # Temple outcrop with carved lintel
        rr = _rng(37)
        outcrop = np.array([(1360, 470), (1395, 360), (1440, 315), (1520, 300), (1610, 310),
                            (1660, 350), (1700, 470)], np.int32)
        m = np.zeros((ch, cw), np.uint8)
        cv2.fillPoly(m, [outcrop], 255, cv2.LINE_AA)
        ma = cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), 2)[..., None]
        boulder = np.array([0.58, 0.53, 0.45]) * (0.55 + 0.7 * tex1) * (0.7 + 0.5 * tex2)
        img = img * (1 - ma) + boulder * ma
        for k in range(10):
            x0 = rr.uniform(1390, 1670)
            y0 = rr.uniform(320, 450)
            cv2.line(img, P(x0, y0), P(x0 + rr.uniform(-25, 25), y0 + rr.uniform(10, 35)), (0.38, 0.33, 0.27), 1)
        img[352:376, 1470:1592] = np.array([0.74, 0.66, 0.52]) * (0.8 + 0.3 * tex2[352:376, 1470:1592])
        img[352:355, 1470:1592] *= 1.15
        img[373:376, 1470:1592] *= 0.5
        for x in range(1476, 1586, 11):
            img[358:369, x:x + 6] *= 0.55
        img[357:371, 1522:1540] = (0.40, 0.35, 0.28)
        img[376:420, 1478:1494] = np.array([0.62, 0.55, 0.44]) * (0.8 + 0.3 * tex2[376:420, 1478:1494])
        img[376:420, 1568:1584] = np.array([0.62, 0.55, 0.44]) * (0.8 + 0.3 * tex2[376:420, 1568:1584])
        img[376:420, 1494:1568] = 0.05
        for k in range(30):
            stone(img, rr.uniform(1480, 1590), rr.uniform(400, 428), rr.uniform(5, 14), rr.uniform(4, 9),
                  rr.uniform(0, 180), (0.62, 0.55, 0.45))

        # Scrub bushes and rocks
        for k in range(320):
            x = rr.uniform(0, cw)
            top = mid_y[int(x)] + 5
            y = rr.uniform(top, ch)
            s = 1.5 + max(0.0, (y - 280)) / 45 * rr.uniform(0.5, 1.3)
            if 1470 < x < 1600 and 350 < y < 420:
                continue
            if rr.random() < 0.55:
                bush(img, x, y, s * 1.4, rr)
            else:
                stone(img, x, y, s * 1.1, s * 0.6, 0, (0.74, 0.66, 0.53))
        speck = rr.random((ch, cw)) > 0.985
        img[speck & (yy > mid_y[None])] *= 0.6
        # Scrub half hiding the doorway
        for (x, y, s) in ((1580, 400, 14), (1598, 388, 10), (1462, 396, 11), (1508, 420, 8)):
            bush(img, x, y, s, rr)

        # Government jeep at the end of the track
        jx, jy = 590, 482
        cv2.ellipse(img, (jx + 5, jy + 2), (62, 9), 0, 0, 360, (0.25, 0.20, 0.15), -1, cv2.LINE_AA)
        body = (0.27, 0.31, 0.20)
        cv2.rectangle(img, (jx - 55, jy - 38), (jx + 25, jy - 10), body, -1)
        cv2.rectangle(img, (jx + 25, jy - 30), (jx + 58, jy - 10), body, -1)
        cv2.rectangle(img, (jx - 55, jy - 62), (jx + 5, jy - 38), (0.43, 0.40, 0.28), -1)
        cv2.line(img, (jx + 22, jy - 30), (jx + 18, jy - 60), (0.15, 0.15, 0.12), 3)
        cv2.line(img, (jx + 18, jy - 60), (jx + 5, jy - 60), (0.15, 0.15, 0.12), 3)
        cv2.rectangle(img, (jx - 50, jy - 34), (jx + 18, jy - 31), (0.18, 0.20, 0.13), -1)
        for wx in (jx - 38, jx + 40):
            cv2.circle(img, (wx, jy - 6), 12, (0.06, 0.06, 0.05), -1, cv2.LINE_AA)
            cv2.circle(img, (wx, jy - 6), 5, (0.35, 0.35, 0.30), -1, cv2.LINE_AA)
        cv2.circle(img, (jx - 60, jy - 26), 11, (0.07, 0.07, 0.06), -1, cv2.LINE_AA)
        cv2.circle(img, (jx + 57, jy - 24), 4, (0.9, 0.9, 0.8), -1, cv2.LINE_AA)
        img[jy - 26:jy - 18, jx - 40:jx - 5] = (0.85, 0.85, 0.80)    # "GOVT" plate-white stripe

        self.base = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 0.6)
        self.shake = Shake(202, fmin=0.4, fmax=3.0)
        self.team = [  # shirt, trousers, pack, carrying case
            ((0.92, 0.90, 0.84), (0.90, 0.88, 0.82), None, None),             # guide, white
            ((0.58, 0.50, 0.33), (0.20, 0.18, 0.16), (0.22, 0.26, 0.18), None),
            ((0.62, 0.62, 0.66), (0.22, 0.20, 0.30), None, (0.12, 0.12, 0.12)),
            ((0.58, 0.50, 0.33), (0.25, 0.22, 0.18), (0.30, 0.24, 0.14), (0.70, 0.70, 0.72)),
            ((0.70, 0.45, 0.35), (0.20, 0.18, 0.16), (0.22, 0.26, 0.18), None),
        ]

    @staticmethod
    def _person(img, x, y, h, phase, move, shirt, pants, pack, case, point=0.0):
        s = h / 100.0
        sw = math.sin(phase) * move
        bob = abs(math.cos(phase)) * 2 * s * move
        hip = np.array([x, y - 50 * s - bob])
        sh = np.array([x, y - 80 * s - bob])
        th = max(1, int(round(6.5 * s)))
        for sg in (1, -1):
            knee = hip + np.array([sg * sw * 6 * s, 25 * s])
            foot = np.array([x + sg * sw * 11 * s, y])
            cv2.line(img, P(*hip), P(*knee), pants, th)
            cv2.line(img, P(*knee), P(*foot), pants, th)
        cv2.line(img, P(*hip), P(*sh), shirt, max(2, int(15 * s)))
        for sg in (1, -1):
            hand = sh + np.array([sg * 9 * s - sg * sw * 7 * s, 28 * s])
            if sg == 1 and point > 0:
                hand = sh + np.array([30 * s * point + 9 * s * (1 - point), (28 - 34 * point) * s])
            cv2.line(img, P(*(sh + [sg * 6 * s, 2 * s])), P(*hand), shirt, max(1, int(5 * s)))
            if case is not None and sg == -1:
                cv2.rectangle(img, P(hand[0] - 7 * s, hand[1]), P(hand[0] + 7 * s, hand[1] + 12 * s), case, -1)
        if pack is not None:
            cv2.rectangle(img, P(x - 9 * s, sh[1] - 2 * s), P(x + 9 * s, sh[1] + 26 * s), pack, -1)
        cv2.circle(img, P(sh[0], sh[1] - 11 * s), max(2, int(7.5 * s)), (0.08, 0.07, 0.06), -1)

    def frame(self, t):
        img = self.base.copy()
        lead = 0.30 + 0.035 * min(t, 7.0)
        people = []
        for i, (shirt, pants, pack, case) in enumerate(self.team):
            stop = 7.0 + 0.15 * i
            gap = 0.055 - 0.012 * ramp(t, 7.0, 7.8)
            u = 0.30 + 0.035 * min(t, stop) - gap * i - (0.01 if i == 3 else 0)
            if i == 3 and 2.6 < t < 4.0:       # the operator's neighbour stumbles on loose stone
                u -= 0.008 * math.sin((t - 2.6) / 1.4 * math.pi)
            move = 1.0 - ramp(t, stop - 0.2, stop + 0.2)
            pos = self.path(u)
            h = 130 - 92 * u
            phase = u * 140 + i * 1.3
            point = ramp(t, 7.3, 7.8) * (1 - ramp(t, 9.8, 10.4)) if i == 0 else 0.0
            people.append((pos[1], pos[0], h, phase, move, shirt, pants, pack, case, point))
        for (y, x, h, phase, move, shirt, pants, pack, case, point) in sorted(people):
            self._person(img, x, y, h, phase, move, shirt, pants, pack, case, point)

        cx = kf(t, [(0, 840), (7.0, 1000), (8.4, 1010), (9.1, 1200), (9.6, 1170), (10.6, 1440),
                    (11.2, 1505), (13, 1528)])
        cy = kf(t, [(0, 405), (7.0, 410), (8.4, 405), (10.6, 385), (13, 382)])
        zm = kf(t, [(0, 0.95), (8.4, 1.0), (10.6, 1.55), (11.5, 2.5), (13, 2.75)])
        g = float(gust(t + 12))
        walk = 1 - ramp(t, 6.8, 7.4)
        sx, sy, sr = self.shake(t)
        bob = abs(math.sin(2 * np.pi * 0.95 * t)) * 7 * walk
        amp = (5 + 6 * walk + 5 * g) / max(1.0, zm ** 0.5)
        frame = view(img, cx + amp * sx, cy + amp * sy + bob, zm, (0.8 + 1.2 * walk) * sr)
        blur = kf(t, [(0, 0.4), (8.8, 0.4), (10.4, 3.5), (11.0, 1.0), (11.5, 4.0), (12.1, 0.2), (13, 0)])
        gain = kf(t, [(0, 1.18), (9, 1.12), (11.5, 0.98), (13, 0.95)])
        return frame, gain, blur, "15:51:%02d" % (18 + int(t))


# ---------------------------------------------------------------------------
# Shared stone-interior helpers
# ---------------------------------------------------------------------------
def stone_tex(h, w, seed, base, course=0):
    t1 = fbm(h, w, 50, 5, seed)[..., None]
    t2 = fbm(h, w, 7, 3, seed + 1)[..., None]
    img = np.asarray(base, np.float32) * (0.6 + 0.6 * t1) * (0.8 + 0.4 * t2)
    if course:
        r = _rng(seed + 2)
        for y in range(0, h, course):
            img[y:y + 3] *= 0.45
            off = r.integers(0, course * 2)
            for x in range(off, w, int(course * 2.2)):
                img[y:y + course, x:x + 3] *= 0.5
    return img.astype(np.float32)


def relief_panel(h, w, seed, base):
    """Weathered rows of carved figures, mostly eroded."""
    img = stone_tex(h, w, seed, base)
    r = _rng(seed + 9)
    lite = np.asarray(base, np.float32) * 1.25
    dark = np.asarray(base, np.float32) * 0.35
    rows = 2
    rh = h // rows
    for row in range(rows):
        y0 = row * rh
        img[y0 + rh - 14:y0 + rh - 4] *= 0.6
        for x in range(40, w - 20, 95):
            cx = x + r.uniform(-6, 6)
            gy = y0 + rh - 20
            for col, off in ((dark, 4), (lite, 0)):
                c = tuple(map(float, col))
                cv2.circle(img, P(cx + off, gy - 125 + off), 13, c, -1)
                cv2.ellipse(img, P(cx + off, gy - 85 + off), (17, 27), 0, 0, 360, c, -1)
                cv2.ellipse(img, P(cx + off, gy - 50 + off), (24, 14), 0, 0, 360, c, -1)
                cv2.line(img, P(cx - 9 + off, gy - 45 + off), P(cx - 12 + off, gy + off), c, 8)
                cv2.line(img, P(cx + 9 + off, gy - 45 + off), P(cx + 14 + off, gy + off), c, 8)
                cv2.line(img, P(cx - 14 + off, gy - 100 + off), P(cx - 36 + off, gy - 120 + off), c, 6)
                cv2.line(img, P(cx + 14 + off, gy - 100 + off), P(cx + 38 + off, gy - 80 + off), c, 6)
            cv2.circle(img, P(cx, gy - 125), 22, tuple(map(float, dark)), 2)
    erode = fbm(h, w, 35, 4, seed + 5)[..., None]
    plain = stone_tex(h, w, seed + 7, base)
    k = smooth((erode - 0.35) / 0.3)
    img = img * (1 - k) + plain * k
    return cv2.GaussianBlur(img, (0, 0), 1.3)


def warp_into(dst, src, quad):
    sh, sw = src.shape[:2]
    Hm = cv2.getPerspectiveTransform(np.float32([(0, 0), (sw, 0), (sw, sh), (0, sh)]), np.float32(quad))
    w = cv2.warpPerspective(src, Hm, (dst.shape[1], dst.shape[0]))
    a = cv2.warpPerspective(np.ones((sh, sw), np.float32), Hm, (dst.shape[1], dst.shape[0]))[..., None]
    dst *= 1 - a
    dst += w * a


def pillar(img, x0, x1, ytop, ybot, seed, broken=False):
    r = _rng(seed)
    h, w = ybot - ytop, x1 - x0
    tex = stone_tex(h, w, seed, (0.60, 0.51, 0.40))
    xs = np.linspace(-1, 1, w)
    shade = (0.35 + 0.75 * np.cos(np.clip(xs + 0.25, -1.4, 1.4) * np.pi / 2.8))[None, :, None]
    col = tex * shade
    for y in range(40, h, 70):
        col[y:y + 10] *= 0.55
        col[y + 10:y + 14] *= 1.25
    m = np.ones((h, w), np.float32)
    if broken:
        jag = (fbm1(w, 6, seed) * 40).astype(int)
        for x in range(w):
            m[:jag[x], x] = 0
    seg = img[ytop:ybot, x0:x1]
    seg[:] = seg * (1 - m[..., None]) + col * m[..., None]
    if not broken:
        img[ytop:ytop + 22, x0 - 10:x1 + 10] = np.array([0.5, 0.42, 0.33]) * shade[:, :1].mean()
    img[ybot - 25:ybot, x0 - 12:x1 + 12] = np.array([0.42, 0.36, 0.29])


def torch(xx, yy, sx, sy, sig, power):
    r2 = (xx - sx) ** 2 + (yy - sy) ** 2
    return power * (np.exp(-r2 / (2 * sig * sig)) + 0.22 * np.exp(-r2 / (2 * (3 * sig) ** 2)))


WARM = np.array([1.0, 0.86, 0.64], np.float32)    # incandescent torch


# ---------------------------------------------------------------------------
# 00:25-00:39  THE TEMPLE
# ---------------------------------------------------------------------------
class Temple:
    CW, CH = 1100, 800

    def __init__(self):
        cw, ch = self.CW, self.CH
        img = np.zeros((ch, cw, 3), np.float32)
        bx0, bx1, by0, by1 = 380, 720, 230, 600
        warp_into(img, stone_tex(300, 900, 41, (0.33, 0.29, 0.24), course=60),
                  [(0, 0), (cw, 0), (bx1, by0), (bx0, by0)])
        warp_into(img, stone_tex(300, 900, 42, (0.46, 0.40, 0.32)),
                  [(bx0, by1), (bx1, by1), (cw, ch), (0, ch)])
        warp_into(img, relief_panel(420, 700, 43, (0.50, 0.43, 0.34)),
                  [(0, 0), (bx0, by0), (bx0, by1), (0, ch)])
        warp_into(img, relief_panel(420, 700, 44, (0.48, 0.42, 0.34))[:, ::-1],
                  [(bx1, by0), (cw, 0), (cw, ch), (bx1, by1)])
        img[by0:by1, bx0:bx1] = stone_tex(by1 - by0, bx1 - bx0, 45, (0.47, 0.41, 0.33), course=46)
        # doorway: lintel, carved jambs, buried slab
        img[275:308, 448:652] = stone_tex(33, 204, 46, (0.58, 0.50, 0.40))
        for x in range(456, 646, 16):
            img[284:298, x:x + 8] *= 0.55
        for (a, b) in ((455, 485), (615, 645)):
            img[308:600, a:b] = stone_tex(292, 30, 47 + a, (0.55, 0.47, 0.38))
            for y in range(316, 600, 26):
                img[y:y + 12, a + 8:b - 8] *= 0.6
        img[308:600, 485:615] = stone_tex(292, 130, 49, (0.32, 0.30, 0.27))
        img[308:600, 485:489] = 0.02                   # the seam
        img[308:312, 485:615] = 0.04
        r = _rng(48)
        for k in range(70):
            x = r.uniform(400, 700)
            y = 600 - abs(r.normal(0, 1)) * 45 * (1 - abs(x - 550) / 220)
            stone(img, x, y, r.uniform(8, 26), r.uniform(6, 16), r.uniform(0, 180), (0.52, 0.45, 0.36))
        pillar(img, 310, 345, 200, 655, 50)
        pillar(img, 755, 790, 380, 655, 51, broken=True)
        pillar(img, 110, 205, 290, 790, 52, broken=True)
        pillar(img, 880, 985, -10 + 30, 800, 53)
        # fallen drum of the broken pillar
        cv2.ellipse(img, (300, 745), (95, 36), 8, 0, 360, (0.30, 0.26, 0.21), -1, cv2.LINE_AA)
        cv2.ellipse(img, (300, 735), (90, 28), 8, 0, 360, (0.50, 0.43, 0.34), -1, cv2.LINE_AA)
        for k in range(160):
            x, y = r.uniform(0, cw), r.uniform(610, 800)
            s = 3 + (y - 600) / 25 * r.uniform(0.4, 1.3)
            stone(img, x, y, s * 1.4, s * 0.8, r.uniform(0, 180), (0.50, 0.43, 0.35))
        grit = fbm(ch, cw, 3, 2, 54)[..., None]
        img *= 0.85 + 0.3 * grit
        self.base = img
        yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
        self.xx, self.yy = xx, yy
        d = np.hypot((xx - 550) / 550, (yy - 415) / 400)
        self.spill = smooth(d - 0.2).astype(np.float32) ** 1.5
        self.shake = Shake(303)
        self.tw = Shake(304, fmin=0.5, fmax=3)

    def _researcher(self, img, t):
        # kneeling at the left jamb, seen from behind, brushing the seam
        dark, khaki, khaki_d = (0.13, 0.12, 0.12), (0.40, 0.35, 0.24), (0.24, 0.21, 0.14)
        cv2.ellipse(img, (430, 600), (55, 10), 0, 0, 360, (0.06, 0.05, 0.05), -1)
        cv2.line(img, (418, 578), (468, 596), dark, 26)            # thigh
        cv2.line(img, (468, 596), (402, 600), dark, 20)            # folded shin
        cv2.ellipse(img, (396, 598), (14, 7), 0, 0, 360, (0.08, 0.07, 0.06), -1)
        torso = np.array([(400, 586), (446, 590), (476, 508), (430, 492)], np.int32)
        cv2.fillPoly(img, [torso], khaki)
        cv2.fillPoly(img, [np.array([(400, 586), (418, 588), (444, 496), (430, 492)], np.int32)], khaki_d)
        cv2.line(img, (412, 586), (448, 588), (0.20, 0.16, 0.10), 5)   # belt
        cv2.circle(img, (458, 478), 17, (0.06, 0.05, 0.05), -1)       # head (hair)
        cv2.ellipse(img, (470, 482), (6, 9), 0, 0, 360, (0.30, 0.20, 0.13), -1)  # ear / cheek
        stroke = math.sin(t * 2 * np.pi * 1.6)
        hand = np.array([486.0, 530 + 28 * stroke])
        elbow = np.array([478.0, 548 + 8 * stroke])
        cv2.line(img, (466, 512), P(*elbow), khaki, 12)
        cv2.line(img, P(*elbow), P(*hand), (0.34, 0.22, 0.14), 9)
        cv2.rectangle(img, P(hand[0] - 2, hand[1] - 10), P(hand[0] + 5, hand[1] + 10), (0.45, 0.33, 0.18), -1)

    def frame(self, t):
        img = self.base.copy()
        if t > 5.6:
            self._researcher(img, t)
        tw = self.tw(t)
        on = 1.0 if t > 0.55 else 0.0
        sx = kf(t, [(0, 600), (0.8, 600), (2.2, 560), (3.5, 250), (4.6, 170), (5.6, 600), (6.8, 930),
                    (7.6, 780), (8.6, 520), (9.6, 490), (14, 488)]) + 12 * tw[0]
        sy = kf(t, [(0, 700), (2.2, 460), (3.5, 420), (4.6, 330), (5.6, 330), (6.8, 380), (7.6, 440),
                    (8.6, 480), (9.6, 470), (14, 470)]) + 10 * tw[1]
        sig = kf(t, [(0, 95), (7.6, 95), (9.6, 55)])
        light = 0.03 + kf(t, [(0, 0.24), (6, 0.16), (14, 0.10)]) * self.spill
        light = light[..., None] + on * torch(self.xx, self.yy, sx, sy, sig, 1.15)[..., None] * WARM
        if t > 5.8:     # the researcher's own lamp on the floor, low and dim
            light += torch(self.xx, self.yy, 520, 585, 70, 0.35 * ramp(t, 5.8, 6.4))[..., None] * WARM
        img = img * light

        cx = kf(t, [(0, 550), (2.5, 545), (5.0, 430), (6.5, 690), (8.2, 555), (14, 540)])
        cy = kf(t, [(0, 430), (2.5, 425), (5.0, 390), (6.5, 390), (8.2, 460), (14, 480)])
        zm = kf(t, [(0, 0.80), (2.5, 0.82), (5.0, 0.95), (6.5, 0.97), (8.6, 1.45), (14, 1.75)])
        s = self.shake(t)
        frame = view(img, cx + 6 * s[0], cy + 5 * s[1], zm, 0.8 * s[2])

        # narrow entrance passage around the lens for the first seconds
        hw = kf(t, [(0, 150), (0.8, 170), (2.8, 420)])
        if hw < 400:
            xcol = np.abs(np.arange(W) - W / 2 + 20 * s[0])
            jag = 12 * fbm1(H, 20, 55)[:, None]
            edge = smooth((xcol[None, :] - hw - jag) / 14)
            rim = np.exp(-((xcol[None, :] - hw - jag) / 10) ** 2) * 0.25 * (1 - ramp(t, 0, 2.5))
            frame = frame * (1 - edge[..., None]) + (0.015 + rim[..., None]) * np.array([0.9, 0.85, 0.75])

        gain = kf(t, [(0, 3.4), (0.6, 3.0), (1.4, 1.8), (2.4, 1.55), (14, 1.5)])
        blur = kf(t, [(0, 5), (0.7, 2), (1.2, 4.5), (1.9, 0.6), (2.6, 0), (7.9, 0), (8.3, 1.6), (8.9, 0)])
        return frame, gain, blur, "16:27:%02d" % (3 + int(t))


# ---------------------------------------------------------------------------
# 00:39-00:51  OPENING
# ---------------------------------------------------------------------------
class Opening:
    CW, CH = 1000, 760
    SEAM = 372

    def __init__(self):
        cw, ch = self.CW, self.CH
        self.jamb = stone_tex(ch, self.SEAM, 61, (0.56, 0.48, 0.38))
        for y in range(10, ch, 46):
            self.jamb[y:y + 22, 250:345] *= 0.55
            cv2.circle(self.jamb, (297, y + 11), 8, (0.62, 0.53, 0.42), -1)
        self.jamb[:, 345:] *= 0.75
        self.slab = stone_tex(ch, cw, 62, (0.42, 0.38, 0.33))
        self.floor = stone_tex(ch, cw, 63, (0.40, 0.34, 0.27))
        r = _rng(64)
        self.stones = []
        for k in range(26):
            x = r.uniform(230, 640)
            y = r.uniform(560, 720)
            self.stones.append([x, y, r.uniform(22, 55) * (0.6 + (y - 540) / 300), r.uniform(15, 35),
                                r.uniform(0, 180), r.uniform(0.85, 1.15)])
        self.stones.sort(key=lambda s: s[1])
        near = sorted(range(len(self.stones)), key=lambda i: abs(self.stones[i][0] - 380) + 0.3 * self.stones[i][1])
        self.lift = {i: 0.3 + 0.55 * j for j, i in enumerate(near[:4])}
        yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.dust = r.random((400, 4))
        self.shake = Shake(404, fmin=0.5, fmax=3.0)
        self.jerk = Shake(405, n=4, fmin=4, fmax=9)

    def gap(self, t):
        steps = [(6.0, 4), (6.7, 3), (7.3, 6), (7.8, 2), (8.3, 7), (8.8, 5), (9.15, 8), (9.55, 45)]
        return sum(g * ramp(t, a, a + 0.12) for a, g in steps)

    def frame(self, t):
        cw, ch = self.CW, self.CH
        img = np.empty((ch, cw, 3), np.float32)
        g = self.gap(t)
        s0 = self.SEAM
        img[:, :s0] = self.jamb
        dx = int(g * 0.5)
        dim = 1 - min(1.0, g / 110)
        img[:, s0:s0 + int(g)] = 0
        img[:, s0 + int(g):] = self.slab[:, s0 - dx:cw - int(g) - dx] * dim if dx else self.slab[:, s0 + int(g):] * dim
        img[:, s0 - 6:s0 + 2] *= 0.15 if g < 2 else 1.0
        img[600:] = np.where(np.arange(cw)[None, :, None] < s0 + g, self.floor[600:], self.floor[600:] * dim)
        img[600:, s0:s0 + int(g)] *= 0.1
        img[598:604] *= 0.4

        # rubble, the top stones lifted away by hand
        hands = []
        for i, (x, y, rx, ry, a, b) in enumerate(self.stones):
            if i in self.lift:
                t0 = self.lift[i]
                u = ramp(t, t0, t0 + 0.55)
                if u >= 1:
                    continue
                x, y = x + 260 * u * u, y - 480 * u
                if t > t0 - 0.25:
                    hands.append((x + rx * 0.4, y - ry * 0.5, ramp(t, t0 - 0.25, t0)))
            stone(img, x, y, rx, ry, a, np.array([0.52, 0.45, 0.36]) * b, seed=600 + i)
        for (hx, hy, k) in hands:
            hx += (1 - k) * 200
            hy += (1 - k) * 160
            cv2.line(img, P(hx + 30, hy + 30), P(hx + 380, hy + 420), (0.15, 0.13, 0.09), 64)
            cv2.line(img, P(hx + 40, hy + 30), P(hx + 380, hy + 410), (0.21, 0.18, 0.12), 26)
            cv2.line(img, P(hx + 8, hy + 8), P(hx + 40, hy + 40), (0.15, 0.10, 0.06), 34)
            cv2.ellipse(img, P(hx, hy), (30, 22), -30, 0, 360, (0.17, 0.11, 0.07), -1)
            for f in range(4):
                cv2.line(img, P(hx - 22 + f * 11, hy - 4), P(hx - 30 + f * 11, hy + 22), (0.15, 0.10, 0.06), 9)

        # crowbar
        if t > 2.5:
            u = ramp(t, 2.5, 3.7)
            tip = np.array([780 + (s0 - 6 - 780) * u, 860 + (470 - 860) * u])
            lev = ramp(t, 5.6, 9.6)
            j = self.jerk(t) * (lev > 0) * (1 - ramp(t, 9.6, 10))
            ang = math.radians(38 - 14 * lev + 2.5 * j[0])
            tip = tip + np.array([g * 0.6, 0])
            end = tip + 1100 * np.array([math.cos(ang), math.sin(ang)])
            cv2.line(img, P(*tip), P(*end), (0.09, 0.09, 0.10), 20)
            cv2.line(img, P(*(tip + [-3, -7])), P(*(end + [-3, -7])), (0.36, 0.35, 0.34), 4)
            grip = tip + 380 * np.array([math.cos(ang), math.sin(ang)])
            cv2.line(img, P(*(grip + [20, 20])), P(*(grip + [300, 380])), (0.15, 0.13, 0.09), 64)
            cv2.ellipse(img, P(*grip), (36, 28), math.degrees(ang), 0, 360, (0.17, 0.11, 0.07), -1)
            cv2.line(img, P(*(grip + [-20, -14])), P(*(grip + [18, -20])), (0.20, 0.13, 0.08), 9)

        tw = self.shake(t * 1.7)
        sx = kf(t, [(0, 420), (2.4, 400), (3.2, 380), (9.6, 385), (12, 395)]) + 10 * tw[0]
        sy = kf(t, [(0, 610), (2.4, 560), (3.2, 480), (9.6, 470), (12, 470)]) + 8 * tw[1]
        light = 0.02 + torch(self.xx, self.yy, sx, sy, 120, 1.5)
        img = img * light[..., None] * WARM

        # dust breathing out of the opened door, caught in the beam
        if t > 9.4:
            age = t - 9.4
            d = self.dust
            px = s0 + g * 0.5 + (d[:, 0] - 0.3) * 60 + age * (30 + 120 * d[:, 2])
            py = 300 + d[:, 1] * 340 - age * (10 + 30 * d[:, 3])
            lit = torch(px, py, sx, sy, 120, 1.0) * 0.9 * np.exp(-age * 0.6)
            for x, y, l in zip(px, py, lit):
                if 0 <= x < cw and 0 <= y < ch and l > 0.03:
                    cv2.circle(img, P(x, y), 1, tuple(map(float, WARM * l)), -1)

        cx = kf(t, [(0, 470), (2.4, 470), (3.0, 430), (5.5, 430), (9.5, 430), (10.6, 400), (12, 392)])
        cy = kf(t, [(0, 600), (2.4, 585), (3.0, 480), (5.5, 470), (9.5, 470), (12, 470)])
        zm = kf(t, [(0, 1.25), (2.4, 1.25), (3.0, 1.45), (5.5, 1.35), (9.5, 1.2), (10.8, 1.9), (12, 2.3)])
        amp = kf(t, [(0, 4), (5.5, 4), (5.8, 9), (9.6, 11), (10.2, 4), (12, 3)])
        s = self.shake(t)
        j = self.jerk(t) * (amp > 6)
        frame = view(img, cx + amp * s[0] + 2 * j[0], cy + amp * s[1] + 2 * j[1], zm, 0.6 * s[2])
        blur = kf(t, [(0, 0.3), (10.4, 0.3), (10.9, 2.0), (11.5, 0.3)])
        return frame, 1.75, blur, "16:39:%02d" % (40 + int(t))


# ---------------------------------------------------------------------------
# 00:51-01:00  THE INNER CHAMBER (ray-cast corbelled dome)
# ---------------------------------------------------------------------------
def _rot(yaw, pitch):
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])
    return Ry @ Rx


class Chamber:
    R = 34.0

    def __init__(self):
        f = (W / 2) / math.tan(math.radians(64) / 2)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.stack([(xx - W / 2) / f, -(yy - H / 2) / f, np.ones_like(xx)], -1)
        self.d = (d / np.linalg.norm(d, axis=-1, keepdims=True)).astype(np.float32)
        self.tex = fbm(512, 2048, 48, 6, 71)
        self.tex2 = fbm(512, 2048, 5, 3, 72)
        self.ftex = fbm(1024, 1024, 20, 5, 73)
        self.cam = np.array([0.0, 1.6, 17.0])
        self.shake = Shake(505, fmin=0.3, fmax=2.0)
        self.tw = Shake(506, fmin=0.6, fmax=3.0)
        self.rng = _rng(507)

    def frame(self, t):
        R = self.R
        settle = 1 - ramp(t, 5.25, 5.7)               # everyone stops after the scuff
        s = self.shake(t) * (0.25 + 0.75 * settle)
        yaw = math.radians(kf(t, [(0, 0), (4.0, 0), (4.4, 4), (6.0, 58), (8.6, 61)]) + 1.2 * s[0])
        pitch = math.radians(kf(t, [(0, 4), (1.2, 7), (4.0, 38), (4.6, 41), (6.0, 36), (8.6, 37)]) + 1.0 * s[1])
        Rm = _rot(yaw, pitch)
        D = self.d @ Rm.T.astype(np.float32)
        Pc = self.cam
        b = D @ Pc
        c = Pc @ Pc - R * R
        ts = -b + np.sqrt(b * b - c)
        dy = D[..., 1]
        tf = np.where(dy < -1e-4, -Pc[1] / np.minimum(dy, -1e-4), np.inf)
        floor = tf < ts
        th = np.minimum(ts, tf)
        X = Pc + D * th[..., None]

        el = np.arcsin(np.clip(X[..., 1] / R, 0, 1))
        az = np.arctan2(X[..., 0], X[..., 2])
        nrows = 64
        hrow = R * np.pi / 2 / nrows
        rowf = el / (np.pi / 2) * nrows
        row = np.floor(rowf)
        fr = rowf - row
        circ = 2 * np.pi * R * np.cos((row + 0.5) / nrows * np.pi / 2)
        M = np.maximum(6, np.round(circ / 1.6))
        colf = (az / (2 * np.pi) + 0.5) * M + 0.5 * (row % 2)
        col = np.floor(colf)
        fc = colf - col
        L = circ / M
        hsh = np.modf(np.abs(np.sin(row * 12.9898 + col * 78.233) * 43758.5453))[0]
        u = ((az / (2 * np.pi) + 0.5) * 2047).astype(np.float32)
        v = (el / (np.pi / 2) * 511).astype(np.float32)
        tx = cv2.remap(self.tex, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        tx2 = cv2.remap(self.tex2, (u * 3) % 2047, (v * 3) % 511, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        alb = (0.30 + 0.25 * hsh) * (0.6 + 0.6 * tx) * (0.8 + 0.4 * tx2)
        mort_r = np.minimum(fr, 1 - fr) * hrow
        mort_c = np.minimum(fc, 1 - fc) * L
        bevel = smooth(np.minimum(mort_r, mort_c) / 0.09)
        alb *= 0.25 + 0.75 * bevel
        fu = ((X[..., 0] * 18) % 1023).astype(np.float32)
        fv = ((X[..., 2] * 18) % 1023).astype(np.float32)
        ft = cv2.remap(self.ftex, fu, fv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        alb = np.where(floor, 0.22 * (0.4 + ft) * (0.6 + 0.6 * smooth((ft - 0.45) / 0.1)), alb)

        # torch: held low-right of the lens, beam climbing the wall
        tw = self.tw(t) * (0.3 + 0.7 * settle)
        T = Pc + Rm @ np.array([0.35, -0.45, 0.25])
        sel = math.radians(kf(t, [(0, 4), (1.0, 6), (4.0, 46), (4.6, 50), (6.0, 44), (8.6, 44)]) + 1.3 * tw[0])
        syw = math.radians(kf(t, [(0, 0), (4.2, 2), (6.0, 63), (8.6, 63)]) + 1.3 * tw[1])
        sd = np.array([math.sin(syw) * math.cos(sel), math.sin(sel), math.cos(syw) * math.cos(sel)])
        V = X - T
        dist = np.linalg.norm(V, axis=-1)
        Vn = V / dist[..., None]
        ang = np.arccos(np.clip(Vn @ sd, -1, 1))
        sig = 0.11
        spot = np.exp(-(ang / sig) ** 2) + 0.12 * np.exp(-(ang / (3.5 * sig)) ** 2)
        N = np.where(floor[..., None], np.array([0, 1.0, 0]), -X / R)
        lam = np.clip(-(Vn * N).sum(-1), 0, 1)
        I = (420 * spot + 30 * np.exp(-(ang / 0.8) ** 2)) * lam / (dist * dist)
        img = (alb * (I + 0.004))[..., None] * WARM

        # visible beam: closest approach between each view ray and the beam axis
        w0 = Pc - T
        bb = D @ sd
        dd = D @ w0
        ee = w0 @ sd
        den = np.maximum(1 - bb * bb, 1e-4)
        sc = (bb * ee - dd) / den
        tc = (ee - bb * dd) / den
        valid = (sc > 0) & (tc > 0) & (sc < th)
        q = w0 + D * sc[..., None] - tc[..., None] * sd
        dq = np.linalg.norm(q, axis=-1)
        width = 0.06 + tc * math.tan(sig * 0.8)
        haze = np.where(valid, np.exp(-(dq / width) ** 2) / (1 + 0.12 * tc), 0)
        sparkle = (self.rng.random((H, W)) > 0.9975) * 2.5
        img += (0.22 * haze * (1 + sparkle))[..., None] * WARM

        # stepping through the gap in the door
        hw = kf(t, [(0, 30), (0.25, 40), (1.4, 420)])
        if hw < 400:
            xcol = np.abs(np.arange(W) - W / 2 - 25 * s[0])
            jag = 10 * fbm1(H, 25, 74)[:, None]
            edge = smooth((xcol[None, :] - hw - jag) / 8)
            rim = np.exp(-((xcol[None, :] - hw - jag) / 6) ** 2) * 0.06
            img = img * (1 - edge[..., None]) + (0.01 + rim[..., None]) * WARM

        return img.astype(np.float32), 1.9, kf(t, [(0, 1.5), (1.4, 0.3)]), "16:48:%02d" % (11 + int(t))


SCENE_CLASSES = {"office": Office, "hills": Hills, "temple": Temple, "opening": Opening, "chamber": Chamber}
