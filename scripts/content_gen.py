#!/usr/bin/env python3
"""
content_gen.py
Calls OpenRouter to invent a fresh topic AND generate all content for it.
Every run = completely new tech horror / digital ghost story.
No hardcoded topics. OpenRouter does everything.

Required env var: OPENROUTER_API_KEY
"""

import os, json, random, time, re, urllib.request, urllib.error

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Models tried in order — first available wins. All are free-tier on OpenRouter.
# Using multiple providers so a single upstream outage doesn't block every run.
MODELS = [
    "arcee-ai/trinity-large-preview:free",      # 400B instruction model — most reliable lately
    "stepfun/step-3.5-flash:free",              # 196B MoE — fast; inline <think> blocks stripped by re.sub
    "nvidia/nemotron-3-super-120b-a12b:free",  # 120B hybrid MoE — last resort
]

# Seed angles so the LLM explores different digital ghost territories
ANGLES = [
    "a username that keeps logging in, but the person died years ago",
    "a server still sending monthly digest emails to an inbox nobody reads",
    "a GitHub repo with a final commit at 3am — author unresponsive since",
    "a Discord account that still shows online, even though the person is gone",
    "a Wayback Machine snapshot of a homepage with a last update that never came",
    "a password reset email sent to an account that no longer exists",
    "an empty chatroom where someone joined but never typed anything",
    "a scheduled tweet that still fires because nobody thought to cancel it",
    "a Google Doc still being edited — but no active users are shown",
    "an IP address that pings back, but the building was demolished years ago",
    "a forum post that still gets replies 11 years after the author was banned",
    "a cloud storage folder shared with a contact who was deleted",
    "a game save file for a character whose last session was on a known date",
    "an email autoresponder that has been running unchanged for 9 years",
    "an SMS delivery receipt for a number that has been disconnected",
]

SYSTEM_PROMPT = """You write content for 30-second vertical horror short videos (YouTube Shorts / Reels).

Each video tells a specific, true-feeling digital ghost story — a haunting on the internet.
Concrete, creepy, unsettling. Treats the internet as haunted infrastructure.
Like a creepypasta crossed with YTP energy and terminal horror.

The video has 5 acts:
1. BOOT — 6 terminal-style "last known activity" log lines (timestamps, idle counters, [warn] notices, unknown sessions)
2. DATA FLOOD — chaotic background, one central fragment from the dead system (IP, 404, offline node)
3. QUESTION — one specific unsettling question about the entity
4. CLIMAX — 8 rapid-cut captions (creepypasta punch + YTP energy: ALL CAPS + lowercase undercut)
5. EPILOGUE — 2-3 quiet haunting lines. A final ping. No response.

You will invent a fresh specific digital ghost story and generate all content for it.

Style rules:
- Boot lines: start with >, use timestamps / idle counters / [warn] prefixes / unknown session notices
- Question: 3-8 words, specific and unsettling (e.g. "Who is still logged in?", "Why did she stop answering?")
- Answers: 1-5 words each, mix technical fragments / eerie possibilities / dead-end answers
- Captions: ALL CAPS for dread, lowercase for ironic undercut, max 5 words each
- Epilogue: short lines, haunting, quiet. Sounds like the internet noticing something wrong.
- YouTube title: plain English. Formats: "The Last [X]", "[Subject] [Action in Year]", "Room 404", "She Never Logged Out", "[Username] Was Here". NO "What It Feels Like To".

Also choose visual style for each act from these options:
- boot_style: "katakana" | "binary" | "hex" | "braille" | "blocks" | "redacted" | "corrupted_log"
  redacted = censored blocks and [REDACTED] strings
  corrupted_log = [ERROR] / [warn] / null / SIGKILL fragments
- flood_style: "green" | "cyan" | "purple" | "amber" | "red"
- question_bg: "hue_shift" | "grid" | "waveform" | "particles" | "static" | "decay" | "vhs_static"
  decay = phosphor-decay vertical streaks on near-black
  vhs_static = horizontal noise bands with tracking artifact
- climax_speed: "slow" (cut every 6f) | "medium" (every 4f) | "fast" (every 2f)
- climax_style: "corrupt" | "digital" | "void" | "haunted"
  corrupt = aggressive noise, harsh glitch, high-contrast palette blocks
  digital = scan lines, grid pulses, scrolling character streams
  void = deep space particles, radial fades, edge glow
  haunted = dead signal noise, phosphor sweep, ghost presence in static
- epilogue_color: "white" | "green" | "cyan" | "amber" | "pink"
- bsod_lines: exactly 3 short strings for a crash screen — topic-specific dark humour,
  technical-sounding (e.g. ["STOP: OWNER_NOT_FOUND (0x00000404)", "0xDEAD  0x4932DAYS", "fatal: session has no owner"])

Palette: pick 3 RGB colors that match the mood. Dark, cold, atmospheric. Favour deep greens, blood reds, amber, near-black.

Respond ONLY with valid JSON. No markdown fences. No explanation."""


def make_prompt(epilogue_extra: str | None = None) -> str:
    angle = random.choice(ANGLES)
    avoid = random.sample(
        [
            "generic haunted house",
            "jump scare",
            "the person was dead all along",
            "possessed device",
            "cursed file download",
            "hacker villain",
            "AI going rogue",
            "social media addiction",
        ],
        3,
    )
    base = f"""Invent a fresh specific digital ghost story for a short horror video.

Ghost angle to explore: {angle}

Avoid these overused tropes: {', '.join(avoid)}

Generate the full video content for your invented story.

Return this exact JSON:
{{
  "title": "your title — formats: The Last [X] | [Subject] [Action in Year] | Room 404 | She Never Logged Out | [Username] Was Here — max 8 words, NO 'What It Feels Like To'",
  "topic_id": "snake_case_identifier",
  "palette": [[r,g,b], [r,g,b], [r,g,b]],
  "boot_style": "katakana|binary|hex|braille|blocks|redacted|corrupted_log",
  "flood_style": "green|cyan|purple|amber|red",
  "question_bg": "hue_shift|grid|waveform|particles|static|decay|vhs_static",
  "climax_speed": "slow|medium|fast",
  "epilogue_color": "white|green|cyan|amber|pink",
  "boot_lines": ["exactly 6 terminal lines starting with > — timestamps, idle counters, [warn] notices"],
  "question": "3-8 word unsettling question about the entity",
  "answers": ["8 to 10 short answers — eerie possibilities, technical fragments, dead-end responses"],
  "captions": [["CAPTION", [r,g,b]], "... 8 total"],
  "epilogue": "line1\\nline2\\noptional line3",
  "bsod_lines": ["STOP: ERROR_NAME (0xCODE)", "0xHEX  0xHEXVALUE", "one-line dark error message"],
  "climax_style": "corrupt|digital|void|haunted"
}}"""
    if epilogue_extra:
        base += f"\n\nEpilogue instruction: {epilogue_extra}"
    return base


def call_llm(prompt: str, model: str) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    payload = json.dumps(
        {
            "model": model,
            "temperature": 1.0,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {e.code} {e.reason}: {body}") from e

    msg = resp["choices"][0]["message"]
    raw = (msg.get("content") or msg.get("reasoning") or "").strip()
    if not raw:
        raise RuntimeError("Model returned empty response")
    # Strip <think>...</think> reasoning blocks (some models include them inline in content)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Strip markdown fences if model adds them
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)


def validate(content: dict) -> dict:
    """Ensure all required fields exist and have correct types."""
    # title
    if not content.get("title"):
        content["title"] = "The Last Ping"

    # topic_id
    if not content.get("topic_id"):
        content["topic_id"] = "unknown"

    # palette — 3 rgb triples
    pal = content.get("palette", [])
    while len(pal) < 3:
        pal.append(
            [random.randint(100, 255), random.randint(50, 200), random.randint(50, 200)]
        )
    content["palette"] = [[max(0, min(255, int(v))) for v in p] for p in pal[:3]]

    # visual style choices
    content["boot_style"] = (
        content.get("boot_style", "corrupted_log")
        if content.get("boot_style")
        in ("katakana", "binary", "hex", "braille", "blocks", "redacted", "corrupted_log")
        else "corrupted_log"
    )
    content["flood_style"] = (
        content.get("flood_style", "green")
        if content.get("flood_style") in ("green", "cyan", "purple", "amber", "red")
        else "green"
    )
    content["question_bg"] = (
        content.get("question_bg", "decay")
        if content.get("question_bg")
        in ("hue_shift", "grid", "waveform", "particles", "static", "decay", "vhs_static")
        else "decay"
    )
    content["climax_speed"] = (
        content.get("climax_speed", "medium")
        if content.get("climax_speed") in ("slow", "medium", "fast")
        else "medium"
    )
    content["epilogue_color"] = (
        content.get("epilogue_color", "white")
        if content.get("epilogue_color") in ("white", "green", "cyan", "amber", "pink")
        else "white"
    )

    # boot_lines
    bl = content.get("boot_lines", [])
    if len(bl) < 6:
        bl += ["> ..."] * (6 - len(bl))
    content["boot_lines"] = bl[:6]

    # question
    if not content.get("question"):
        content["question"] = "What am I?"

    # answers
    ans = content.get("answers", [])
    if len(ans) < 8:
        ans += ["..."] * (8 - len(ans))
    content["answers"] = ans[:10]

    # captions
    caps = content.get("captions", [])
    fixed = []
    for cap in caps:
        if isinstance(cap, list) and len(cap) == 2:
            text = str(cap[0])
            color = (
                cap[1]
                if isinstance(cap[1], list) and len(cap[1]) == 3
                else [255, 255, 255]
            )
            fixed.append([text, [max(0, min(255, int(v))) for v in color]])
    while len(fixed) < 8:
        fixed.append(["...", [200, 200, 200]])
    content["captions"] = fixed[:8]

    # epilogue
    if not content.get("epilogue"):
        content["epilogue"] = "I exist.\nSomewhat."

    # bsod_lines — 3 topic-specific crash screen strings
    bl = content.get("bsod_lines", [])
    if not isinstance(bl, list) or len(bl) < 3:
        tid = content.get("topic_id", "unknown").upper().replace("_", " ")
        h = abs(hash(content.get("topic_id", "x")))
        bl = [
            f"STOP: {tid[:18]}_FAULT",
            f"0x{h % 0xFFFF:04X}  0x00FEELINGS",
            "A fatal exception has occurred.",
        ]
    content["bsod_lines"] = [str(x)[:60] for x in bl[:3]]

    # climax_style
    content["climax_style"] = (
        content.get("climax_style", "haunted")
        if content.get("climax_style") in ("corrupt", "digital", "void", "haunted")
        else "haunted"
    )

    return content


def fallback() -> dict:
    """Return one of several pre-written topics so repeated LLM failures don't produce identical videos."""
    return random.choice(_FALLBACK_POOL)


_FALLBACK_POOL = [
  {
    "title": "The Server That Never Went Offline",
        "topic_id": "server_never_offline",
        "palette": [[20, 200, 80], [180, 0, 40], [200, 180, 0]],
        "boot_style": "corrupted_log",
        "flood_style": "green",
        "question_bg": "decay",
        "climax_speed": "medium",
        "epilogue_color": "green",
        "boot_lines": [
            "> LAST PING: 2011-08-22 03:14:09",
            "> STATUS: IDLE  uptime: 4932 days",
            "> [warn] owner contact: UNRESOLVABLE",
            "> [warn] hosting payment: LAPSED 2018",
            "> [warn] 3 active sessions — origin: UNKNOWN",
            "> ...",
        ],
        "question": "Who is still logged in?",
        "answers": [
            "no one",
            "the original owner",
            "automated",
            "a scheduled job",
            "nobody knows",
            "still pinging",
            "ghost process",
            "undefined user",
        ],
        "captions": [
            ["IT SHOULDN'T BE ONLINE", [200, 80, 80]],
            ["but it is", [150, 60, 60]],
            ["4932 DAYS", [200, 200, 0]],
            ["SOMEONE LOGGED IN", [220, 80, 80]],
            ["AT 3AM", [180, 40, 40]],
            ["no record", [100, 100, 100]],
            ["still there", [80, 200, 80]],
            ["THE LAST PING", [255, 255, 255]],
        ],
        "epilogue": "The server is still running.\nNobody remembers why.\nNobody turned it off.",
        "bsod_lines": [
            "STOP: OWNER_NOT_FOUND (0x00000404)",
            "0xDEAD  0x4932DAYS",
            "fatal: session has no owner",
        ],
        "climax_style": "haunted",
  },
  {
    "title": "She Never Logged Out",
    "topic_id": "never_logged_out",
    "palette": [[0, 160, 255], [80, 0, 120], [255, 60, 60]],
    "boot_style": "redacted",
    "flood_style": "cyan",
    "question_bg": "vhs_static",
    "climax_speed": "fast",
    "epilogue_color": "cyan",
    "boot_lines": [
        "> LAST ACTIVE: 2017-11-03 22:14:51",
        "> SESSION: still open (2811 days)",
        "> [warn] account flagged: inactive owner",
        "> [warn] login origin: [REDACTED]",
        "> [warn] password reset requested: 14 times",
        "> STATUS: online",
    ],
    "question": "Why is she still online?",
    "answers": [
        "she isn't",
        "automatic",
        "a cached session",
        "a ghost process",
        "someone else",
        "no one knows",
        "the app never closed",
        "undefined",
    ],
    "captions": [
        ["LAST SEEN", [0, 160, 255]],
        ["2017", [0, 120, 200]],
        ["STILL ONLINE", [255, 60, 60]],
        ["how", [80, 80, 200]],
        ["SHE NEVER CLOSED IT", [200, 60, 200]],
        ["nobody thought to", [100, 100, 180]],
        ["still there", [0, 200, 255]],
        ["ALWAYS ONLINE", [255, 255, 255]],
    ],
    "epilogue": "The session is still open.\nShe just never came back.\nThe app never noticed.",
    "bsod_lines": [
        "STOP: USER_UNREACHABLE (0x00002017)",
        "0xDEAD  0x0SESSION",
        "fatal: owner.respond() timeout",
    ],
    "climax_style": "void",
  },
  {
    "title": "The Last Commit",
    "topic_id": "last_commit",
    "palette": [[0, 255, 100], [200, 40, 40], [255, 200, 0]],
    "boot_style": "corrupted_log",
    "flood_style": "green",
    "question_bg": "decay",
    "climax_speed": "medium",
    "epilogue_color": "amber",
    "boot_lines": [
        "> git log --oneline HEAD",
        "> a3f09c1 fix: final adjustment (3am)",
        "> [warn] author: no further commits",
        "> [warn] issues: 7 open, 0 responses",
        "> [warn] last clone: 4 years ago",
        "> repo still public.",
    ],
    "question": "Who made the last commit?",
    "answers": [
        "he did",
        "at 3am",
        "then nothing",
        "no message",
        "no PR",
        "no response",
        "repo still there",
        "still cloneable",
    ],
    "captions": [
        ["3AM COMMIT", [200, 200, 0]],
        ["no message", [150, 150, 0]],
        ["NEVER MERGED", [200, 40, 40]],
        ["7 open issues", [160, 40, 40]],
        ["nobody answered", [120, 120, 120]],
        ["repo still public", [0, 200, 80]],
        ["still cloneable", [0, 160, 60]],
        ["THE LAST COMMIT", [255, 255, 255]],
    ],
    "epilogue": "The repo is still there.\nThe issues are still open.\nHe never pushed again.",
    "bsod_lines": [
        "STOP: AUTHOR_MISSING (0x00000000)",
        "0xDEAD  0xC0MMIT",
        "fatal: remote HEAD unreachable",
    ],
    "climax_style": "haunted",
  },
]


def generate_topic(epilogue_extra: str | None = None) -> dict:
    """Generate a completely fresh topic and all content via OpenRouter."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    print(f"  OPENROUTER_API_KEY: {'SET (' + key[:8] + '...)' if key else 'NOT SET'}")
    prompt = make_prompt(epilogue_extra)
    for i, model in enumerate(MODELS):
        try:
            print(f"  Generating topic (model: {model})...")
            content = call_llm(prompt, model)
            content = validate(content)
            print(f"  Topic: '{content['title']}'")
            print(f"  Question: '{content['question']}'")
            return content
        except Exception as e:
            print(f"  {model} failed: {e}")
            if i < len(MODELS) - 1:
                print("  Waiting 5s before trying next model...")
                time.sleep(5)
    print("  All models failed. Using fallback content.")
    return fallback()


if __name__ == "__main__":
    import sys

    content = generate_topic()
    print(json.dumps(content, indent=2))
