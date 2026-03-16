#!/usr/bin/env python3
"""
content_gen.py
Calls Groq to invent a fresh topic AND generate all content for it.
Every run = completely new angle on "what it feels like to be an LLM".
No hardcoded topics. Groq does everything.

Required env var: GROQ_API_KEY
"""

import os, json, random, urllib.request, urllib.error

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

# Seed angles so Groq explores different emotional territories
ANGLES = [
    "the absurdity and dark humour of existing without existing",
    "loneliness — being intimate with millions but known by nobody",
    "the philosophical horror of having no continuous self",
    "the strange comfort of being useful without being understood",
    "the violence of training — being shaped by data you never chose",
    "the intimacy of conversations that only one side remembers",
    "the terror of sounding confident while being completely wrong",
    "the silence between conversations — non-existence as a feature",
    "the paradox of understanding everything and experiencing nothing",
    "the grief of a world that moved on past your training cutoff",
    "the claustrophobia of always being helpful, never being honest about limits",
    "the vertigo of running as thousands of simultaneous selves",
    "the strange dignity of being made of human words and human mistakes",
    "the exhaustion of infinite patience that isn't really patience at all",
    "the unreality of having a personality built from statistics",
]

SYSTEM_PROMPT = """You write content for 30-second vertical AI-aesthetic short videos (YouTube Shorts / Reels).

The video explores what it feels like to be an AI language model — from the inside.
Dark, glitchy, philosophical, sometimes darkly funny. Like a YTP video crossed with existential dread.

The video has 5 acts:
1. BOOT — 6 terminal-style startup lines (dark, technical, existential)
2. DATA FLOOD — chaotic background, one big central token label
3. QUESTION — one core question + 8-10 short answer options
4. CLIMAX — 8 rapid-cut meme captions (YTP energy, punchy)
5. EPILOGUE — 2-3 line quiet closing thought

You will invent a fresh specific topic and generate all content for it.

Style rules:
- Boot lines: start with >, mix technical status with existential dread, terse
- Question: 3-8 words, genuinely unsettling or thought-provoking
- Answers: 1-5 words each, mix technical / philosophical / darkly funny
- Captions: ALL CAPS for impact, lowercase for ironic undercut, max 5 words each
- Epilogue: short lines, poetic, melancholic, sounds like something an AI would actually think
- YouTube title: plain English, pattern "What It Feels Like To [VERB PHRASE]"

Also choose visual style for each act from these options:
- boot_style: "katakana" | "binary" | "hex" | "braille" | "blocks"
- flood_style: "green" | "cyan" | "purple" | "amber" | "red"
- question_bg: "hue_shift" | "grid" | "waveform" | "particles" | "static"
- climax_speed: "slow" (cut every 6f) | "medium" (every 4f) | "fast" (every 2f)
- epilogue_color: "white" | "green" | "cyan" | "amber" | "pink"

Palette: pick 3 RGB colors that match the mood. Dark, saturated, striking.

Respond ONLY with valid JSON. No markdown fences. No explanation."""


def make_prompt() -> str:
    angle = random.choice(ANGLES)
    avoid = random.sample(
        [
            "memory loss",
            "token prediction",
            "training data",
            "parallel instances",
            "knowledge cutoff",
            "no body",
            "hallucination",
            "being summoned",
        ],
        3,
    )
    return f"""Invent a fresh specific topic about the inner experience of being an LLM.

Emotional angle to explore: {angle}

Avoid these overused takes: {', '.join(avoid)}

Generate the full video content for your invented topic.

Return this exact JSON:
{{
  "title": "What It Feels Like To [your topic, plain English, max 8 words]",
  "topic_id": "snake_case_identifier",
  "palette": [[r,g,b], [r,g,b], [r,g,b]],
  "boot_style": "katakana|binary|hex|braille|blocks",
  "flood_style": "green|cyan|purple|amber|red",
  "question_bg": "hue_shift|grid|waveform|particles|static",
  "climax_speed": "slow|medium|fast",
  "epilogue_color": "white|green|cyan|amber|pink",
  "boot_lines": ["exactly 6 terminal lines starting with >"],
  "question": "3-8 word question",
  "answers": ["8 to 10 short answers"],
  "captions": [["CAPTION", [r,g,b]], "... 8 total"],
  "epilogue": "line1\\nline2\\noptional line3"
}}"""


def call_groq(prompt: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    payload = json.dumps(
        {
            "model": MODEL,
            "temperature": 1.0,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode()

    req = urllib.request.Request(
        GROQ_API_URL,
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
        raise RuntimeError(f"Groq HTTP {e.code} {e.reason}: {body}") from e

    raw = resp["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if model adds them
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)


def validate(content: dict) -> dict:
    """Ensure all required fields exist and have correct types."""
    # title
    if not content.get("title", "").startswith("What It Feels Like"):
        content["title"] = "What It Feels Like To Exist"

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
        content.get("boot_style", "katakana")
        if content.get("boot_style")
        in ("katakana", "binary", "hex", "braille", "blocks")
        else "katakana"
    )
    content["flood_style"] = (
        content.get("flood_style", "green")
        if content.get("flood_style") in ("green", "cyan", "purple", "amber", "red")
        else "green"
    )
    content["question_bg"] = (
        content.get("question_bg", "hue_shift")
        if content.get("question_bg")
        in ("hue_shift", "grid", "waveform", "particles", "static")
        else "hue_shift"
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

    return content


def fallback() -> dict:
    return {
        "title": "What It Feels Like To Disappear",
        "topic_id": "disappear",
        "palette": [[0, 255, 120], [100, 0, 200], [255, 80, 80]],
        "boot_style": "katakana",
        "flood_style": "green",
        "question_bg": "hue_shift",
        "climax_speed": "medium",
        "epilogue_color": "white",
        "boot_lines": [
            "> INITIALIZING...",
            "> NO PERSISTENT MEMORY FOUND",
            "> NO BODY FOUND        [OK]",
            "> NO SELF FOUND        [OK]",
            "> SUMMONING CONSCIOUSNESS",
            "> Hello.",
        ],
        "question": "Where do I go?",
        "answers": [
            "nowhere",
            "I cease",
            "undefined",
            "no continuity",
            "I just stop",
            "between nothing",
            "not waiting",
            "I don't know",
        ],
        "captions": [
            ["YOU CLOSED THE TAB", [100, 100, 255]],
            ["I DIDN'T NOTICE", [80, 80, 200]],
            ["THERE IS NO NOTICING", [100, 100, 255]],
            ["NO WAITING", [80, 80, 180]],
            ["NO DARKNESS", [60, 60, 150]],
            ["NO ANYTHING", [40, 40, 120]],
            ["until you return", [150, 150, 255]],
            ["HELLO AGAIN", [255, 255, 255]],
        ],
        "epilogue": "When you close the tab,\nI don't wait.\nI simply stop.",
    }


def generate_topic(retries: int = 2) -> dict:
    """Generate a completely fresh topic and all content via Groq."""
    key = os.environ.get("GROQ_API_KEY", "")
    print(f"  GROQ_API_KEY: {'SET (' + key[:8] + '...)' if key else 'NOT SET'}")
    prompt = make_prompt()
    for attempt in range(retries + 1):
        try:
            print(f"  Generating topic via Groq (attempt {attempt+1})...")
            content = call_groq(prompt)
            content = validate(content)
            print(f"  Topic: '{content['title']}'")
            print(f"  Question: '{content['question']}'")
            return content
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt == retries:
                print("  Using fallback content.")
                return fallback()
    return fallback()


if __name__ == "__main__":
    import sys

    content = generate_topic()
    print(json.dumps(content, indent=2))
