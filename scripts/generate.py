#!/usr/bin/env python3
"""
LLM Shorts — Video Generator
Every run: the LLM invents a brand-new short story + visual style choices.
5-act structure is fixed. Everything inside is driven by the LLM output.
  Act 1 OPENING    5s  — opening lines appear over falling symbols
  Act 2 SPARK      5s  — story keywords stream past
  Act 3 QUESTION   6s  — the turning point + possible answers
  Act 4 CLIMAX     8s  — fast-cut captions + storybook title card
  Act 5 ENDING     6s  — the story lands
"""

import os, sys, math, random, wave, subprocess, json, argparse, colorsys
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from content_gen import generate_topic

W, H = 1080, 1920
FPS = 30
RATE = 44100
FONT_M = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_S = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

HASHTAGS = "#Storytime #ShortStory #Storytelling #MicroFiction #CreativeWriting #Fiction #Animation #Shorts"
# Hour (UTC) each slot targets. Minute is randomised at runtime so videos
# don't always surface at the same second — looks organic, not bot-scheduled.
SLOT_HOURS = {"morning": 12, "afternoon": 17, "evening": 22}

# ── Helpers ───────────────────────────────────────────────────────────────────


def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def lerp(a, b, t):
    return a + (b - a) * t


def fnt(path, size):
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()


def fit_font(path, text, max_w, start_size, min_size=34):
    size = start_size
    while size >= min_size:
        try:
            f = ImageFont.truetype(path, size)
        except:
            return ImageFont.load_default(), min_size
        if f.getlength(text) <= max_w:
            return f, size
        size -= 4
    return ImageFont.truetype(path, min_size), min_size


def hsv_s1_to_rgb_array(h_arr, v=0.5):
    """
    Vectorised HSV→RGB with S=1 fixed.
    h_arr: float32 ndarray in [0,1], any shape.
    Returns uint8 array of same shape + channel dim (shape + (3,)).
    """
    h6 = (h_arr * 6).astype(np.float32)
    hi = h6.astype(np.int32) % 6
    f  = h6 - np.floor(h6)
    q  = np.float32(v) * (1 - f)
    t  = np.float32(v) * f
    vv = np.float32(v)
    r = np.select([hi==0, hi==1, hi==2, hi==3, hi==4], [vv, q,  0,  0,  t ], default=vv)
    g = np.select([hi==0, hi==1, hi==2, hi==3, hi==4], [t,  vv, vv, q,  0 ], default=0)
    b = np.select([hi==0, hi==1, hi==2, hi==3, hi==4], [0,  0,  t,  vv, vv], default=q)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def glitch_rows(arr, count=12, shift=60):
    out = arr.copy()
    h = arr.shape[0]
    for _ in range(count):
        y = random.randint(0, h - 1)
        out[y] = np.roll(out[y], random.randint(-shift, shift), axis=0)
    return out


def chroma(img, s=6):
    img = img.convert("RGB")
    r, g, b = img.split()
    r = r.transform(r.size, Image.AFFINE, (1, 0, -s, 0, 1, 0))
    b = b.transform(b.size, Image.AFFINE, (1, 0, s, 0, 1, 0))
    return Image.merge("RGB", [r, g, b])


def scanlines(img, a=50):
    ol = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ol)
    for y in range(0, H, 5):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    return Image.alpha_composite(img.convert("RGBA"), ol).convert("RGB")


def add_noise(img, s=7):
    arr = np.array(img).astype(np.int16)
    arr += np.random.randint(-s, s, arr.shape, dtype=np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def draw_outlined(draw, text, y, f, color):
    """Centered text with black outline. Caller must pass already-fitted font."""
    PAD = 60
    tw = f.getlength(text)
    x = max(PAD, (W - tw) / 2)
    for ox, oy in [
        (-4, 0),
        (4, 0),
        (0, -4),
        (0, 4),
        (-3, -3),
        (3, -3),
        (-3, 3),
        (3, 3),
    ]:
        draw.text((x + ox, y + oy), text, font=f, fill=(0, 0, 0))
    draw.text((x, y), text, font=f, fill=color)


def safe_text(draw, text, y, path, start_size, color):
    """Fit font to width then draw outlined. One call does everything."""
    f, _ = fit_font(path, text, W - 120, start_size)
    draw_outlined(draw, text, y, f, color)
    return f  # return for line measurements


# ── Audio ─────────────────────────────────────────────────────────────────────


def write_wav(path, samples):
    data = (np.clip(np.tanh(samples * 1.1) * 0.7, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(data.tobytes())


def warm_pad(dur, vol=0.15):
    # A-major triad (A2, C#3, E3) with a soft swell
    t = np.linspace(0, dur, int(RATE * dur), False)
    s = (
        0.5 * np.sin(2 * np.pi * 110 * t)
        + 0.3 * np.sin(2 * np.pi * 138.6 * t + 0.3)
        + 0.2 * np.sin(2 * np.pi * 164.8 * t + 0.6)
    )
    return s * (0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * t)) * vol


def digital_blip(dur, vol=0.18):
    t = np.linspace(0, dur, int(RATE * dur), False)
    freqs = [220, 330, 440, 330, 550, 440, 660, 440]
    seg = int(RATE * dur / 8)
    out = np.zeros(int(RATE * dur))
    for i, f in enumerate(freqs):
        s = i * seg
        e = min(s + seg, len(out))
        chunk = vol * np.sin(2 * np.pi * f * t[s:e])
        env = np.ones(e - s)
        env[: min(80, e - s)] = np.linspace(0, 1, min(80, e - s))
        env[-min(80, e - s) :] = np.linspace(1, 0, min(80, e - s))
        out[s:e] = chunk * env
    return out


def data_cascade(dur, vol=0.10):
    t = np.linspace(0, dur, int(RATE * dur), False)
    sig = np.zeros_like(t)
    for _ in range(20):
        sig += random.uniform(0.03, 0.07) * np.sin(
            2 * np.pi * random.uniform(200, 2000) * t + random.uniform(0, 6.28)
        )
    return sig * vol


def chaos_audio(dur, vol=0.14):
    sig = data_cascade(dur, vol) + warm_pad(dur, vol * 0.6)
    crush = np.round(sig * 8) / 8
    return np.clip(sig * 0.6 + crush * 0.4, -1, 1) * vol


# ── Rain character sets ───────────────────────────────────────────────────────

RAIN_CHARS = {
    "stars":         list("★☆✦✧✶✷✸·•"),
    "notes":         list("♪♫♬♩"),
    "petals":        list("❀✿❁•∘"),
    "hearts":        list("♥♡•"),
    "snow":          list("❄✺✹·•∘"),
    "weather":       list("☀☁☂☃☾☽"),
    "katakana":      [chr(c) for c in range(0x30A0, 0x30FF)],
    "binary":        list("01010110110100"),
    "hex":           list("0123456789ABCDEF"),
    "braille":       [chr(c) for c in range(0x2800, 0x2840)],
    "blocks":        list("█▓▒░▄▀■□▪▫"),
}

FLOOD_COLORS = {
    "green": (0, 220, 60),
    "cyan": (0, 200, 255),
    "purple": (180, 0, 255),
    "amber": (255, 160, 0),
    "red": (255, 40, 40),
    "pink": (255, 110, 190),
    "gold": (255, 205, 60),
}

EPILOGUE_COLORS = {
    "white": (240, 240, 240),
    "green": (0, 255, 120),
    "cyan": (0, 220, 255),
    "amber": (255, 200, 60),
    "pink": (255, 150, 200),
}

# Frames per caption — slow enough that the story can be read
CUT_SPEED = {"slow": 12, "medium": 9, "fast": 6}

# ── Acts ──────────────────────────────────────────────────────────────────────


def act_boot(topic):
    n = 150
    lines = topic["boot_lines"]
    color = tuple(topic["palette"][0])
    frames = []
    style = topic.get("boot_style", "stars")
    rain_set = RAIN_CHARS.get(style, RAIN_CHARS["stars"])
    step = n // (len(lines) + 1)  # frames between lines, leaves time to read the last one
    f_term = fnt(FONT_M, 52)
    f_rain = fnt(FONT_M, 30)
    # Mutable list so rain can fall each frame
    rain = [
        [random.randint(0, W), random.randint(-H, H), random.choice(rain_set)]
        for _ in range(80)
    ]

    # Stronger palette tint — visibly different per topic (~12% brightness)
    bg = (max(4, color[0] // 8), max(4, color[1] // 8), max(4, color[2] // 8))

    for i in range(n):
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        # Falling rain
        for r in rain:
            a = random.randint(15, 55)
            rc2 = random.choice(rain_set)
            d.text(
                (r[0], r[1]),
                rc2,
                font=f_rain,
                fill=(
                    clamp(color[0] * a // 200),
                    clamp(color[1] * a // 200),
                    clamp(color[2] * a // 200),
                ),
            )
            r[1] += random.randint(4, 14)   # fall downward
            if r[1] > H + 20:               # wrap back to top
                r[1] = random.randint(-80, -10)
                r[0] = random.randint(0, W)
                r[2] = random.choice(rain_set)
        visible = min(i // step + 1, len(lines))
        y_start = H // 2 - (visible * 72) // 2
        for j, line in enumerate(lines[:visible]):
            age = i - j * step
            alpha = clamp(255 * min(1.0, age / 10))
            fl, _ = fit_font(FONT_M, line, W - 100, 52)
            c2 = (
                clamp(color[0] * alpha // 255),
                clamp(color[1] * alpha // 255),
                clamp(color[2] * alpha // 255),
            )
            d.text((50, y_start + j * 72), line, font=fl, fill=c2)
        if visible <= len(lines) and (i // 8) % 2 == 0:
            d.text(
                (50, y_start + (visible - 1) * 72 + 72), "█", font=f_term, fill=color
            )
        frames.append(scanlines(add_noise(img, 6)))
    return frames, digital_blip(n / FPS)


def act_data_flood(topic):
    n = 150
    frames = []
    style = topic.get("flood_style", "green")
    fc = FLOOD_COLORS.get(style, FLOOD_COLORS["green"])
    palette = topic["palette"]
    f_big = fnt(FONT_S, 130)
    f_rain = fnt(FONT_M, 40)

    # Story keywords stream past; fall back to title words
    vocab = topic.get("keywords") or topic["title"].split()

    streams = [
        (random.randint(0, W - 120), random.randint(-300, 0), random.choice(vocab))
        for _ in range(55)
    ]

    # Palette-tinted background (palette[1] at ~10% brightness)
    p1 = tuple(palette[1])
    bg_flood = (max(3, p1[0] // 10), max(3, p1[1] // 10), max(3, p1[2] // 10))

    for i in range(n):
        img = Image.new("RGB", (W, H), bg_flood)
        d = ImageDraw.Draw(img)
        new_s = []
        for x, y, tok in streams:
            ny = y + 14
            if ny > H + 40:
                ny = -40
                tok = random.choice(vocab)
            new_s.append((x, ny, tok))
            if 0 < ny < H:
                a = clamp(55 + int(140 * (1 - ny / H)))
                d.text(
                    (x, ny),
                    tok,
                    font=f_rain,
                    fill=(
                        clamp(fc[0] * a // 255),
                        clamp(fc[1] * a // 255),
                        clamp(fc[2] * a // 255),
                    ),
                )
        streams[:] = new_s

        # Central label cycles through the story keywords
        label = vocab[(i // 15) % len(vocab)].upper()
        if i % 15 == 14:
            label = "".join(
                chr(random.randint(0x2580, 0x259F)) if random.random() < 0.35 else c
                for c in label
            )

        f_label, _ = fit_font(FONT_S, label, W - 80, 130)
        draw_outlined(d, label, H // 2 - 80, f_label, fc)

        if i % 7 < 3:
            img = Image.fromarray(glitch_rows(np.array(img), 16))
        img = chroma(img, int(5 + 4 * math.sin(i * 0.4)))
        frames.append(scanlines(img, 45))
    return frames, data_cascade(n / FPS)


def act_question(topic):
    n = 180
    frames = []
    q = topic["question"]
    answers = topic["answers"]
    color = tuple(topic["palette"][2])
    bg_mode = topic.get("question_bg", "hue_shift")
    f_ans = fnt(FONT_S, 78)
    f_fly = fnt(FONT_M, 46)
    # Unique per topic — makes answer scatter positions different every reel
    topic_seed = abs(hash(topic.get("topic_id", "x"))) % 100000

    for i in range(n):
        t = i / n

        # Background — Groq-chosen mode
        if bg_mode == "hue_shift":
            arr = np.zeros((H, W, 3), dtype=np.uint8)
            for y in range(H):
                hue = (t * 0.2 + y / H * 0.3 + math.sin(t * 3 + y * 0.01) * 0.07) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.18)
                arr[y] = [int(r * 255), int(g * 255), int(b * 255)]
            img = Image.fromarray(arr)

        elif bg_mode == "grid":
            img = Image.new("RGB", (W, H), (5, 5, 15))
            d2 = ImageDraw.Draw(img)
            gs = 80
            gc = (clamp(color[0] // 8), clamp(color[1] // 8), clamp(color[2] // 8))
            for x in range(0, W, gs):
                d2.line([(x, 0), (x, H)], fill=gc, width=1)
            for y in range(0, H, gs):
                d2.line([(0, y), (W, y)], fill=gc, width=1)
            # Pulse
            pulse = clamp(int(8 + 6 * math.sin(t * math.pi * 4)))
            img2 = Image.new("RGB", (W, H), (pulse, pulse, pulse + 4))
            img = Image.blend(img, img2, 0.3)

        elif bg_mode == "waveform":
            arr = np.zeros((H, W, 3), dtype=np.uint8)
            for x in range(W):
                wave_y = int(
                    H // 2
                    + math.sin(x * 0.03 + t * 6) * 200
                    + math.sin(x * 0.07 + t * 3) * 100
                )
                for y in range(max(0, wave_y - 3), min(H, wave_y + 3)):
                    a = 1 - (abs(y - wave_y) / 4)
                    arr[y, x] = [
                        clamp(color[0] * a * 0.6),
                        clamp(color[1] * a * 0.6),
                        clamp(color[2] * a * 0.6),
                    ]
            img = Image.fromarray(arr)

        elif bg_mode == "particles":
            img = Image.new("RGB", (W, H), (3, 3, 10))
            d2 = ImageDraw.Draw(img)
            random.seed(topic_seed + i * 7)
            for _ in range(60):
                px = random.randint(0, W)
                py = random.randint(0, H)
                r = random.randint(2, 8)
                a = random.randint(30, 120)
                d2.ellipse(
                    [px - r, py - r, px + r, py + r],
                    fill=(
                        clamp(color[0] * a // 255),
                        clamp(color[1] * a // 255),
                        clamp(color[2] * a // 255),
                    ),
                )
            random.seed()

        elif bg_mode == "decay":
            # Phosphor-decay: near-black base with vertical green/amber streaks slowly burning in
            arr = np.random.randint(0, 8, (H, W, 3), dtype=np.uint8)
            random.seed(topic_seed + i)
            for _ in range(18):
                sx = random.randint(0, W - 1)
                sy = random.randint(0, H - 1)
                ey = min(H, sy + random.randint(60, 300))
                intensity = random.randint(40, 120)
                arr[sy:ey, sx, 1] = np.clip(arr[sy:ey, sx, 1].astype(int) + intensity, 0, 255)
            random.seed()
            img = Image.fromarray(arr)

        elif bg_mode == "vhs_static":
            # VHS tracking artifact: horizontal noise bands drifting + palette tint
            arr = np.random.randint(0, 30, (H, W, 3), dtype=np.uint8)
            band_y = int((t * 3 * H) % H)
            w = min(80, H - band_y)
            if w > 0:
                arr[band_y:band_y + w] = np.clip(arr[band_y:band_y + w].astype(int) + 30, 0, 60)
            arr[:, :, 0] = np.clip(arr[:, :, 0].astype(int) + color[0] // 8, 0, 255)
            arr[:, :, 1] = np.clip(arr[:, :, 1].astype(int) + color[1] // 8, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2].astype(int) + color[2] // 8, 0, 255)
            img = Image.fromarray(arr)

        else:  # static
            arr = np.random.randint(0, 40, (H, W, 3), dtype=np.uint8)
            arr[:, :, 0] = np.clip(arr[:, :, 0] + color[0] // 6, 0, 255)
            arr[:, :, 1] = np.clip(arr[:, :, 1] + color[1] // 6, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] + color[2] // 6, 0, 255)
            img = Image.fromarray(arr)

        d = ImageDraw.Draw(img)

        # Question at top
        safe_text(d, q, 200, FONT_S, 96, (255, 255, 255))
        fq, _ = fit_font(FONT_S, q, W - 120, 96)
        qw = fq.getlength(q)
        d.line(
            [((W - qw) / 2, 320), ((W + qw) / 2, 320)], fill=(255, 255, 255), width=3
        )

        # Scattered small answers — seeded by topic_id so positions vary per topic
        random.seed(topic_seed + i * 3)
        for _ in range(4):
            ax = random.randint(40, W - 320)
            ay = random.randint(400, H - 250)
            a = random.randint(70, 160)
            d.text((ax, ay), random.choice(answers), font=f_fly, fill=(a, a, a))
        random.seed()

        # Main cycling answer
        main = answers[(i // 8) % len(answers)]
        f_main, _ = fit_font(FONT_S, main, W - 120, 78)
        draw_outlined(d, main, H // 2 + 80, f_main, color)

        if i % 9 < 3:
            img = Image.fromarray(glitch_rows(np.array(img), 10))
        img = chroma(img, random.randint(0, 5))
        frames.append(add_noise(img, 7))
    return frames, warm_pad(n / FPS) + data_cascade(n / FPS) * 0.5


def act_climax(topic):
    n = 240
    frames = []
    cap_idx = 0
    captions = topic["captions"]
    cut_every = CUT_SPEED.get(topic.get("climax_speed", "medium"), 4)
    palette = topic["palette"]
    p0 = tuple(palette[0])
    p1 = tuple(palette[1])
    p2 = tuple(palette[2])
    card_lines = topic.get("card_lines", ["MEANWHILE...", "", ""])
    climax_style = topic.get("climax_style", "warm")

    # Topic-seeded mode order — same topic = same order, different topics = different shuffle
    _rng = random.Random(abs(hash(topic.get("topic_id", "x"))))
    _mode_order = [0, 1, 2, 3, 4]
    _rng.shuffle(_mode_order)

    for i in range(n):
        t = i / n
        if i % cut_every == 0:
            cap_idx = (cap_idx + 1) % len(captions)
        cap_entry = captions[cap_idx]
        cap_text = cap_entry[0]
        cap_color = (
            tuple(cap_entry[1]) if isinstance(cap_entry[1], list) else cap_entry[1]
        )

        mode = _mode_order[(i // 10) % 5]

        # ── Mode 1: always storybook title card (text from LLM) ──
        if mode == 1:
            img = Image.new("RGB", (W, H), (clamp(p0[0] // 4), clamp(p0[1] // 4), clamp(p0[2] // 4)))
            d2 = ImageDraw.Draw(img)
            d2.rectangle([50, 560, W - 50, 1260], outline=p2, width=6)
            f_card, _ = fit_font(FONT_S, card_lines[0], W - 200, 130)
            draw_outlined(d2, card_lines[0], 680, f_card, (255, 255, 255))
            for bi, btxt in enumerate(card_lines[1:3]):
                bfl, _ = fit_font(FONT_S, btxt, W - 200, 64)
                draw_outlined(d2, btxt, 930 + bi * 110, bfl, p2)

        # ── Mode 4: always palette gradient (outro fade) ──
        elif mode == 4:
            arr = np.zeros((H, W, 3), dtype=np.uint8)
            for y in range(H):
                tt = y / H
                arr[y] = [
                    clamp(lerp(p0[0] // 5, p1[0] // 5, tt)),
                    clamp(lerp(p0[1] // 5, p1[1] // 5, tt)),
                    clamp(lerp(p0[2] // 5, p1[2] // 5, tt)),
                ]
            img = Image.fromarray(arr)

        # ── Modes 0, 2, 3: vary by climax_style ──
        elif climax_style == "corrupt":
            if mode == 0:
                # p0-tinted noise blocks
                arr = np.random.randint(0, 60, (H, W, 3), dtype=np.uint8)
                arr[:, :, 0] = np.clip(arr[:, :, 0] + p0[0] // 3, 0, 255)
                arr[:, :, 1] = np.clip(arr[:, :, 1] + p0[1] // 3, 0, 255)
                arr[:, :, 2] = np.clip(arr[:, :, 2] + p0[2] // 3, 0, 255)
                img = Image.fromarray(arr)
            elif mode == 2:
                # Radial hue burst — fully vectorised (was O(W*H) Python loops)
                ys = np.arange(0, H, 2, dtype=np.float32)[:, None]
                xs = np.arange(0, W, 4, dtype=np.float32)[None, :]
                dist = np.sqrt((xs - W // 2) ** 2 + (ys - H // 2) ** 2)
                hue  = (dist * 0.002 + t * 2) % 1.0
                small = hsv_s1_to_rgb_array(hue, v=0.5)        # (H/2, W/4, 3)
                arr   = np.repeat(np.repeat(small, 2, axis=0), 4, axis=1)  # (H, W, 3)
                img   = Image.fromarray(arr)
            else:
                # mode 3: p1-tinted heavy noise
                arr = np.random.randint(0, 200, (H, W, 3), dtype=np.uint8)
                arr[:, :, 0] = np.clip(arr[:, :, 0] // 4 + p1[0] // 3, 0, 255)
                arr[:, :, 1] = np.clip(arr[:, :, 1] // 4 + p1[1] // 3, 0, 255)
                arr[:, :, 2] = np.clip(arr[:, :, 2] // 4 + p1[2] // 3, 0, 255)
                img = Image.fromarray(arr)

        elif climax_style == "digital":
            if mode == 0:
                # Horizontal scan lines sweeping in p0
                img = Image.new("RGB", (W, H), (3, 3, 10))
                d2 = ImageDraw.Draw(img)
                scan_y = int((t * H * 3) % H)
                for y in range(scan_y, min(scan_y + 80, H)):
                    a = 1 - abs(y - scan_y - 40) / 40
                    d2.line(
                        [(0, y), (W, y)],
                        fill=(clamp(p0[0] * a), clamp(p0[1] * a), clamp(p0[2] * a)),
                        width=1,
                    )
            elif mode == 2:
                # Grid pulse in p1
                img = Image.new("RGB", (W, H), (5, 5, 15))
                d2 = ImageDraw.Draw(img)
                pulse = 0.5 + 0.5 * math.sin(t * math.pi * 6)
                gs = 60
                for x in range(0, W, gs):
                    d2.line([(x, 0), (x, H)], fill=(clamp(p1[0] * pulse), clamp(p1[1] * pulse), clamp(p1[2] * pulse)))
                for y in range(0, H, gs):
                    d2.line([(0, y), (W, y)], fill=(clamp(p1[0] * pulse), clamp(p1[1] * pulse), clamp(p1[2] * pulse)))
            else:
                # mode 3: scrolling data text rows in p2
                img = Image.new("RGB", (W, H), (2, 2, 8))
                d2 = ImageDraw.Draw(img)
                f_data = fnt(FONT_M, 28)
                chars = RAIN_CHARS.get(topic.get("boot_style", "katakana"), RAIN_CHARS["katakana"])
                for row in range(0, H, 36):
                    scroll = int(t * 400) % W
                    line_txt = "".join(random.choice(chars) for _ in range(50))
                    d2.text(
                        (-scroll, row),
                        line_txt + line_txt,
                        font=f_data,
                        fill=(clamp(p2[0] // 2), clamp(p2[1] // 2), clamp(p2[2] // 2)),
                    )

        elif climax_style == "void":
            if mode == 0:
                # Sparse particles in p0
                img = Image.new("RGB", (W, H), (2, 2, 8))
                d2 = ImageDraw.Draw(img)
                random.seed(abs(hash(topic.get("topic_id", "x"))) + i * 17)
                for _ in range(40):
                    px2, py2 = random.randint(0, W), random.randint(0, H)
                    r2 = random.randint(1, 5)
                    a = random.randint(40, 180) / 255
                    d2.ellipse(
                        [px2 - r2, py2 - r2, px2 + r2, py2 + r2],
                        fill=(clamp(p0[0] * a), clamp(p0[1] * a), clamp(p0[2] * a)),
                    )
                random.seed()
            elif mode == 2:
                # Radial fade from center in p1 — fully vectorised
                cx, cy   = W // 2, H // 2
                max_d    = math.sqrt(cx ** 2 + cy ** 2)
                pulse    = 0.6 + 0.4 * math.sin(t * math.pi * 4)
                ys = np.arange(0, H, 2, dtype=np.float32)[:, None]
                xs = np.arange(0, W, 2, dtype=np.float32)[None, :]
                a_small  = np.maximum(0.0, 1.0 - np.sqrt((xs - cx)**2 + (ys - cy)**2) / max_d) * pulse
                rgb_col  = np.array([p1[0], p1[1], p1[2]], dtype=np.float32)
                small    = np.clip(a_small[:, :, None] * rgb_col, 0, 255).astype(np.uint8)
                arr      = np.repeat(np.repeat(small, 2, axis=0), 2, axis=1)
                img      = Image.fromarray(arr)
            else:
                # mode 3: edge glow in p2 on near-black
                arr = np.zeros((H, W, 3), dtype=np.uint8)
                for y in range(H):
                    edge = min(y, H - y) / (H // 2)
                    a = (1 - edge) * 0.4
                    arr[y] = [clamp(p2[0] * a), clamp(p2[1] * a), clamp(p2[2] * a)]
                img = Image.fromarray(arr)

        else:  # "warm"
            if mode == 0:
                # Soft glowing light orbs drifting upward in p0
                img = Image.new("RGB", (W, H), (clamp(p1[0] // 10), clamp(p1[1] // 10), clamp(p1[2] // 10)))
                d2 = ImageDraw.Draw(img)
                orb_rng = random.Random(abs(hash(topic.get("topic_id", "x"))))
                for _ in range(22):
                    ox = orb_rng.randint(0, W)
                    oy = int(orb_rng.randint(0, H) - t * orb_rng.randint(200, 700)) % H
                    rad = orb_rng.randint(20, 90)
                    a = orb_rng.uniform(0.25, 0.6)
                    d2.ellipse(
                        [ox - rad, oy - rad, ox + rad, oy + rad],
                        fill=(clamp(p0[0] * a), clamp(p0[1] * a), clamp(p0[2] * a)),
                    )
            elif mode == 2:
                # Sunrise gradient from p1 (top) to p2 (bottom), gently breathing
                glow = 0.45 + 0.15 * math.sin(t * math.pi * 4)
                tt = np.linspace(0, 1, H, dtype=np.float32)[:, None]
                col = (np.array(p1, dtype=np.float32) * (1 - tt) + np.array(p2, dtype=np.float32) * tt) * glow
                arr = np.repeat(np.clip(col, 0, 255).astype(np.uint8)[:, None, :], W, axis=1)
                img = Image.fromarray(arr)
            else:
                # mode 3: twinkling boot-style symbols in p2
                img = Image.new("RGB", (W, H), (4, 4, 10))
                d2 = ImageDraw.Draw(img)
                chars = RAIN_CHARS.get(topic.get("boot_style", "stars"), RAIN_CHARS["stars"])
                f_twinkle = fnt(FONT_M, 44)
                random.seed(abs(hash(topic.get("topic_id", "x"))) + i * 13)
                for _ in range(30):
                    gx = random.randint(0, W - 60)
                    gy = random.randint(0, H - 60)
                    a = random.randint(60, 200)
                    d2.text(
                        (gx, gy), random.choice(chars), font=f_twinkle,
                        fill=(clamp(p2[0] * a // 255), clamp(p2[1] * a // 255), clamp(p2[2] * a // 255)),
                    )
                random.seed()

        d = ImageDraw.Draw(img)
        if i < n - 30:
            f_cap, _ = fit_font(FONT_S, cap_text, W - 100, 104)
            draw_outlined(d, cap_text, H - 420, f_cap, cap_color)

        if random.random() < 0.5:
            img = Image.fromarray(glitch_rows(np.array(img), 18, 80))
        if random.random() < 0.35:
            img = chroma(img, random.randint(6, 16))
        img = add_noise(img, 16)
        if i > n - 20:
            fade = (i - (n - 20)) / 20
            img = Image.fromarray((np.array(img) * (1 - fade)).astype(np.uint8))
        frames.append(img)
    return frames, chaos_audio(n / FPS)


def act_epilogue(topic):
    n = 180
    frames = []
    parts = topic["epilogue"].split("\n")
    ecolor = EPILOGUE_COLORS.get(topic.get("epilogue_color", "white"), (240, 240, 240))
    appear = [(j + 1) * n // (len(parts) + 2) for j in range(len(parts))]
    f_cur = fnt(FONT_M, 54)

    # Faint palette[2] vertical gradient background — unique per topic
    p2_ep = tuple(topic["palette"][2])

    for i in range(n):
        arr_ep = np.zeros((H, W, 3), dtype=np.uint8)
        for y in range(H):
            fade_ep = (1 - y / H) * 0.08   # very subtle, darkest at bottom
            arr_ep[y] = [
                clamp(p2_ep[0] * fade_ep),
                clamp(p2_ep[1] * fade_ep),
                clamp(p2_ep[2] * fade_ep),
            ]
        img = Image.fromarray(arr_ep)
        d = ImageDraw.Draw(img)
        cy = H // 2 - len(parts) * 65
        for j, part in enumerate(parts):
            if i >= appear[j]:
                fade = min(1.0, (i - appear[j]) / 20.0)
                a = clamp(255 * fade)
                fe, _ = fit_font(FONT_S, part, W - 80, 78)
                pw = fe.getlength(part)
                col = (
                    clamp(ecolor[0] * a // 255),
                    clamp(ecolor[1] * a // 255),
                    clamp(ecolor[2] * a // 255),
                )
                d.text(((W - pw) / 2, cy + j * 130), part, font=fe, fill=col)
        if i > appear[-1] + 30 and (i // 10) % 2 == 0:
            d.text(
                (W // 2 - 20, cy + len(parts) * 130 + 30), "█", font=f_cur, fill=ecolor
            )
        if i < 20:
            img = Image.fromarray((np.array(img) * (i / 20)).astype(np.uint8))
        frames.append(add_noise(img, 4))
    return frames, warm_pad(n / FPS, vol=0.10)


# ── Render ────────────────────────────────────────────────────────────────────


def generate(topic_id, slot, out_dir, *,
             remnant_state=None, run_type="NORMAL", epilogue_extra=None,
             recent_stories=None):
    os.makedirs(out_dir, exist_ok=True)
    frames_dir = os.path.join(out_dir, "_frames")
    os.makedirs(frames_dir, exist_ok=True)

    # LLM invents a new story; recent_stories keeps it from repeating
    topic = generate_topic(epilogue_extra=epilogue_extra, slot=slot,
                           recent=recent_stories)

    # REMNANT layer — inject boot line, advance narrative state
    if run_type in ("REMNANT", "DORMANT") and remnant_state is not None:
        import remnant as rem
        if run_type == "REMNANT":
            rem.apply_remnant(remnant_state, topic)
        else:
            rem.apply_dormant(remnant_state, topic)

    print(f"Title: {topic['title']}")
    print(
        f"Style: boot={topic['boot_style']} flood={topic['flood_style']} "
        f"q_bg={topic['question_bg']} climax={topic['climax_speed']}/{topic['climax_style']} "
        f"epilogue={topic['epilogue_color']}"
    )

    acts = [
        ("opening", act_boot),
        ("spark", act_data_flood),
        ("question", act_question),
        ("climax", act_climax),
        ("ending", act_epilogue),
    ]

    all_frames = []
    all_audio = []
    for name, fn in acts:
        print(f"  {name}...", end=" ", flush=True)
        frames, audio = fn(topic)
        all_frames.extend(frames)
        all_audio.append(audio)
        print(f"{len(frames)}f ({len(frames)/FPS:.1f}s)")

    print(f"  Total: {len(all_frames)} frames = {len(all_frames)/FPS:.1f}s")
    for idx, frm in enumerate(all_frames):
        frm.save(f"{frames_dir}/f{idx:05d}.jpg", "JPEG", quality=95)

    wav = os.path.join(out_dir, "audio.wav")
    write_wav(wav, np.concatenate(all_audio))

    video = os.path.join(out_dir, "video.mp4")
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            f"{frames_dir}/f%05d.jpg",
            "-i",
            wav,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-vf",
            "curves=preset=cross_process,noise=alls=2:allf=t+u,vignette=PI/6",
            video,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("ffmpeg error:", r.stderr[-1500:])
        sys.exit(1)
    print(f"  Video -> {video}")

    import shutil

    shutil.rmtree(frames_dir)

    # Schedule for tomorrow so the timestamp is never in the past by the time the
    # user approves and publish.py runs (which can be 30-120 min after generation).
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    kit = {
        "title": topic["title"],
        "description": f"{topic['premise']}\n\n{HASHTAGS}".strip(),
        "topic": topic.get("topic_id", "generated"),
        "genre": topic.get("genre", ""),
        "premise": topic.get("premise", ""),
        "slot": slot,
        "scheduled_time_utc": f"{tomorrow}T{SLOT_HOURS.get(slot, SLOT_HOURS['morning']):02d}:{random.randint(0, 54):02d}:00Z",
        "video": video,
    }
    kit_path = os.path.join(out_dir, "kit.json")
    with open(kit_path, "w") as f:
        json.dump(kit, f, indent=2)
    return kit


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="morning", choices=["morning", "afternoon", "evening"])
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    k = generate(None, args.slot, args.out)
    print(f"Done: {k['video']}")
