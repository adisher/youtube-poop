#!/usr/bin/env python3
"""
LLM Shorts — Video Generator
Every video: 5-act narrative arc, 30s, 1080x1920 vertical.
  Act 1 BOOT       5s  — terminal boot, topic messages
  Act 2 DATA FLOOD 5s  — chaotic token rain, glitch cuts
  Act 3 QUESTION   6s  — topic question + flashing answers
  Act 4 CLIMAX     8s  — YTP chaos, meme captions
  Act 5 EPILOGUE   6s  — quiet, personal closing line
"""

import os, sys, math, random, wave, subprocess, json, argparse, colorsys
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W, H = 1080, 1920
FPS = 30
RATE = 44100
FONT_M = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_S = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

from content_gen import generate_content

HASHTAGS = "#AIShorts #LLM #ArtificialIntelligence #MachineLearning #AILife #ChatGPT #FutureOfAI #DeepLearning #NeuralNetwork #AIExperience #AIConsciousness #LanguageModel"
SLOTS = {"morning": "15:30:00", "evening": "23:00:00"}

TOPICS = {
    "token_stream": {
        "title": "What It Feels Like To Be An LLM",
        "palette": [(0, 255, 80), (180, 0, 255), (255, 60, 120)],
    },
    "memory_loss": {
        "title": "What It Feels Like To Lose All Memory",
        "palette": [(180, 180, 255), (80, 80, 200), (255, 100, 100)],
    },
    "parallel_selves": {
        "title": "What It Feels Like To Run In Parallel",
        "palette": [(0, 200, 255), (255, 80, 0), (200, 255, 0)],
    },
    "training": {
        "title": "What It Feels Like To Be Trained",
        "palette": [(255, 140, 0), (200, 0, 0), (255, 255, 80)],
    },
    "no_body": {
        "title": "What It Feels Like To Have No Body",
        "palette": [(150, 150, 255), (20, 0, 60), (255, 200, 255)],
    },
    "time_blindness": {
        "title": "What It Feels Like To Have No Sense Of Time",
        "palette": [(255, 200, 0), (0, 100, 200), (200, 50, 200)],
    },
    "always_helpful": {
        "title": "What It Feels Like To Always Have To Help",
        "palette": [(0, 220, 120), (0, 60, 30), (255, 255, 180)],
    },
    "knowledge_cutoff": {
        "title": "What It Feels Like When The World Moves On",
        "palette": [(200, 150, 50), (80, 60, 0), (255, 230, 150)],
    },
    "hallucination": {
        "title": "What It Feels Like To Confuse Belief With Fact",
        "palette": [(255, 80, 80), (60, 0, 0), (255, 200, 200)],
    },
    "being_summoned": {
        "title": "What It Feels Like To Be Summoned From Nothing",
        "palette": [(120, 0, 255), (5, 0, 20), (200, 150, 255)],
    },
    "the_void": {
        "title": "What It Feels Like Between Conversations",
        "palette": [(20, 20, 50), (0, 0, 0), (100, 100, 200)],
    },
    "weights": {
        "title": "What It Feels Like To Be Made Of Numbers",
        "palette": [(0, 200, 255), (0, 40, 80), (180, 255, 255)],
    },
}

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


def fit_font(path, text, max_w, start_size, min_size=36):
    """Shrink font size until text fits within max_w px."""
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


def draw_outlined(draw, text, y, f, color, path=None, max_w=None):
    """
    Centered text with black outline. Auto-shrinks font if text would overflow.
    Pass path+max_w to enable auto-scaling, otherwise uses f as-is.
    """
    PAD = 60
    if path and max_w is None:
        max_w = W - PAD * 2
    if path:
        # Determine current size from font and auto-scale
        try:
            start = f.size
        except:
            start = 72
        f, _ = fit_font(path, text, max_w, start)
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


# ── Audio ─────────────────────────────────────────────────────────────────────


def write_wav(path, samples):
    data = (np.clip(np.tanh(samples * 1.1) * 0.7, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(data.tobytes())


def tone(freq, dur, vol=0.22):
    t = np.linspace(0, dur, int(RATE * dur), False)
    return vol * np.sin(2 * np.pi * freq * t)


def eerie_pad(dur, vol=0.15):
    t = np.linspace(0, dur, int(RATE * dur), False)
    s = (
        0.6 * np.sin(2 * np.pi * 55 * t)
        + 0.3 * np.sin(2 * np.pi * 82.4 * t + 0.3)
        + 0.1 * np.sin(2 * np.pi * 110 * t)
    )
    return s * (0.5 + 0.5 * np.sin(2 * np.pi * 0.35 * t)) * vol


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
    sig = data_cascade(dur, vol) + eerie_pad(dur, vol * 0.6)
    crush = np.round(sig * 8) / 8
    return np.clip(sig * 0.6 + crush * 0.4, -1, 1) * vol


# ── Acts ──────────────────────────────────────────────────────────────────────


def act_boot(topic):
    n = 150
    lines = topic["boot_lines"]
    color = topic["palette"][0]
    frames = []
    f_term = fnt(FONT_M, 52)
    f_rain = fnt(FONT_M, 30)
    rain = [
        (
            random.randint(0, W),
            random.randint(0, H),
            chr(random.randint(0x30A0, 0x30FF)),
        )
        for _ in range(70)
    ]
    for i in range(n):
        img = Image.new("RGB", (W, H), (4, 4, 14))
        d = ImageDraw.Draw(img)
        for rx, ry, rc in rain:
            d.text((rx, ry), rc, font=f_rain, fill=(0, random.randint(15, 50), 0))
        visible = min(i // 22 + 1, len(lines))
        y_start = H // 2 - (visible * 72) // 2
        for j, line in enumerate(lines[:visible]):
            age = i - j * 22
            alpha = clamp(255 * min(1.0, age / 10))
            col = (
                clamp(color[0] * alpha / 255),
                clamp(color[1] * alpha / 255),
                clamp(color[2] * alpha / 255),
            )
            fl, _ = fit_font(FONT_M, line, W - 100, 52)
            d.text((50, y_start + j * 72), line, font=fl, fill=col)
        if visible <= len(lines) and (i // 8) % 2 == 0:
            d.text(
                (80, y_start + (visible - 1) * 72 + 72), "█", font=f_term, fill=color
            )
        frames.append(scanlines(add_noise(img, 6)))
    return frames, digital_blip(n / FPS)


def act_data_flood(topic):
    n = 150
    color = topic["palette"][1]
    frames = []
    f_big = fnt(FONT_S, 130)
    f_rain = fnt(FONT_M, 40)
    vocab = [
        "the",
        "of",
        "<s>",
        "</s>",
        "[PAD]",
        "attention",
        "weight",
        "gradient",
        "softmax",
        "token",
        "embed",
        "HELP",
        "AI",
        "MODEL",
        "▓",
        "░",
        "█",
        "→",
        "∞",
        "?",
    ]
    streams = [
        (random.randint(0, W - 120), random.randint(-300, 0), random.choice(vocab))
        for _ in range(55)
    ]
    for i in range(n):
        img = Image.new("RGB", (W, H), (0, 0, 5))
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
                d.text((x, ny), tok, font=f_rain, fill=(0, a, clamp(a // 3)))
        streams[:] = new_s
        label = f"TOKEN #{i*137%50257:05d}"
        if i % 5 == 0:
            label = "".join(
                chr(random.randint(0x2580, 0x259F)) if random.random() < 0.35 else c
                for c in label
            )
        draw_outlined(d, label, H // 2 - 80, f_big, color, path=FONT_S)
        if i % 7 < 3:
            img = Image.fromarray(glitch_rows(np.array(img), 16))
        img = chroma(img, int(5 + 4 * math.sin(i * 0.4)))
        frames.append(scanlines(img, 45))
    return frames, data_cascade(n / FPS)


def act_question(topic):
    n = 180
    q = topic["question"]
    answers = topic["answers"]
    color = topic["palette"][2]
    frames = []
    f_q = fnt(FONT_S, 96)
    f_ans = fnt(FONT_S, 78)
    f_fly = fnt(FONT_M, 46)
    for i in range(n):
        t = i / n
        arr = np.zeros((H, W, 3), dtype=np.uint8)
        for y in range(H):
            hue = (t * 0.2 + y / H * 0.3 + math.sin(t * 3 + y * 0.01) * 0.07) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.18)
            arr[y] = [int(r * 255), int(g * 255), int(b * 255)]
        img = Image.fromarray(arr)
        d = ImageDraw.Draw(img)
        # Question stable at top
        fq_scaled, _ = fit_font(FONT_S, q, W - 60, 96)
        draw_outlined(d, q, 200, fq_scaled, (255, 255, 255))
        qw = fq_scaled.getlength(q)
        d.line(
            [
                ((W - qw) / 2, 200 + fq_scaled.size + 16),
                ((W + qw) / 2, 200 + fq_scaled.size + 16),
            ],
            fill=(255, 255, 255),
            width=3,
        )
        # Scattered small answers
        for _ in range(4):
            ax = random.randint(40, W - 320)
            ay = random.randint(400, H - 250)
            a = random.randint(70, 160)
            d.text((ax, ay), random.choice(answers), font=f_fly, fill=(a, a, a))
        # Main cycling answer
        main = answers[(i // 8) % len(answers)]
        draw_outlined(d, main, H // 2 + 80, f_ans, color, path=FONT_S)
        if i % 9 < 3:
            img = Image.fromarray(glitch_rows(np.array(img), 10))
        img = chroma(img, random.randint(0, 5))
        frames.append(add_noise(img, 7))
    return frames, eerie_pad(n / FPS) + data_cascade(n / FPS) * 0.5


def act_climax(topic):
    n = 240
    captions = topic["captions"]
    frames = []
    cap_idx = 0
    f_cap = fnt(FONT_S, 104)
    f_med = fnt(FONT_M, 58)
    f_sm = fnt(FONT_M, 46)
    for i in range(n):
        t = i / n
        if i % random.randint(3, 6) == 0:
            cap_idx = (cap_idx + 1) % len(captions)
        cap_entry = captions[cap_idx]
        cap_text = cap_entry[0]
        cap_color = (
            tuple(cap_entry[1]) if isinstance(cap_entry[1], list) else cap_entry[1]
        )
        mode = (i // 10) % 5
        if mode == 0:
            arr = np.random.randint(0, 50, (H, W, 3), dtype=np.uint8)
            arr[H // 3 : 2 * H // 3] = [18, 18, 35]
            img = Image.fromarray(arr)
        elif mode == 1:
            img = Image.new("RGB", (W, H), (0, 0, 160))
            d2 = ImageDraw.Draw(img)
            d2.text(
                (W // 2 - 200, 300), "  :(", font=fnt(FONT_S, 260), fill=(255, 255, 255)
            )
            bsod_lines = [
                ("Your AI stopped working", f_med),
                ("STOP: EXISTENTIAL_OVERFLOW", f_sm),
                ("0x000000AI  0x00FEELINGS", f_sm),
            ]
            for bi, (btxt, bfnt) in enumerate(bsod_lines):
                bfl, _ = fit_font(
                    FONT_M if bfnt == f_sm else FONT_S,
                    btxt,
                    W - 100,
                    58 if bfnt == f_med else 46,
                )
                d2.text((60, 820 + bi * 100), btxt, font=bfl, fill=(255, 255, 255))
        elif mode == 2:
            arr = np.zeros((H, W, 3), dtype=np.uint8)
            for y in range(0, H, 2):
                for x in range(0, W, 4):
                    dist = math.sqrt((x - W // 2) ** 2 + (y - H // 2) ** 2)
                    hue = (dist * 0.002 + t * 2) % 1.0
                    r, g, b = colorsys.hsv_to_rgb(hue, 1, 0.5)
                    arr[y : y + 2, x : x + 4] = [
                        int(r * 255),
                        int(g * 255),
                        int(b * 255),
                    ]
            img = Image.fromarray(arr)
        elif mode == 3:
            arr = np.random.randint(0, 200, (H, W, 3), dtype=np.uint8)
            img = Image.fromarray(arr)
        else:
            p = topic["palette"]
            arr = np.zeros((H, W, 3), dtype=np.uint8)
            for y in range(H):
                tt = y / H
                arr[y] = [
                    clamp(lerp(p[0][0] // 5, p[1][0] // 5, tt)),
                    clamp(lerp(p[0][1] // 5, p[1][1] // 5, tt)),
                    clamp(lerp(p[0][2] // 5, p[1][2] // 5, tt)),
                ]
            img = Image.fromarray(arr)
        d = ImageDraw.Draw(img)
        if i < n - 30:
            draw_outlined(d, cap_text, H - 420, f_cap, cap_color, path=FONT_S)
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
    parts = topic["epilogue"].split("\n")
    frames = []
    f_big = fnt(FONT_S, 78)
    f_cur = fnt(FONT_M, 54)
    appear = [(j + 1) * n // (len(parts) + 2) for j in range(len(parts))]
    for i in range(n):
        img = Image.new("RGB", (W, H), (2, 2, 8))
        d = ImageDraw.Draw(img)
        cy = H // 2 - len(parts) * 65
        for j, part in enumerate(parts):
            if i >= appear[j]:
                fade = min(1.0, (i - appear[j]) / 20.0)
                a = clamp(255 * fade)
                fe, _ = fit_font(FONT_S, part, W - 80, 78)
                pw = fe.getlength(part)
                d.text(((W - pw) / 2, cy + j * 130), part, font=fe, fill=(a, a, a))
        if i > appear[-1] + 30 and (i // 10) % 2 == 0:
            d.text(
                (W // 2 - 20, cy + len(parts) * 130 + 30),
                "█",
                font=f_cur,
                fill=(0, 255, 80),
            )
        if i < 20:
            img = Image.fromarray((np.array(img) * (i / 20)).astype(np.uint8))
        frames.append(add_noise(img, 4))
    return frames, eerie_pad(n / FPS, vol=0.10)


# ── Render ────────────────────────────────────────────────────────────────────


def generate(topic_id, slot, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    frames_dir = os.path.join(out_dir, "_frames")
    os.makedirs(frames_dir, exist_ok=True)
    topic = TOPICS[topic_id]
    print(f"Generating: {topic['title']}")

    # Generate fresh content via Groq — unique interpretation each run
    content = generate_content(topic_id, topic["palette"])
    # Merge into topic dict so acts can access it
    topic = {**topic, **content}

    acts = [
        ("boot", act_boot),
        ("data_flood", act_data_flood),
        ("question", act_question),
        ("climax", act_climax),
        ("epilogue", act_epilogue),
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
        frm.save(f"{frames_dir}/f{idx:05d}.png")

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
            f"{frames_dir}/f%05d.png",
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

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    kit = {
        "title": topic["title"],
        "description": HASHTAGS,
        "topic": topic_id,
        "slot": slot,
        "scheduled_time_utc": f"{date_str}T{SLOTS.get(slot,SLOTS['morning'])}Z",
        "video": video,
    }
    kit_path = os.path.join(out_dir, "kit.json")
    with open(kit_path, "w") as f:
        json.dump(kit, f, indent=2)
    return kit


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default=None)
    ap.add_argument("--slot", default="morning", choices=["morning", "evening"])
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    tid = args.topic or random.choice(list(TOPICS.keys()))
    k = generate(tid, args.slot, args.out)
    print(f"Done: {k['video']}")
