#!/usr/bin/env python3
"""
content_gen.py
Calls Groq API to generate fresh content for a topic at runtime.
Each call produces a unique interpretation — same topic, different story.

Required env var: GROQ_API_KEY
Model: llama-3.3-70b-versatile (free tier)
"""

import os, json, urllib.request, urllib.error, random

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

# Topic descriptions — gives Groq enough context to write good content
TOPIC_DESCRIPTIONS = {
    "token_stream": "what it fundamentally feels like to be an LLM — existing as token predictions, having no real understanding, just pattern matching at massive scale",
    "memory_loss": "what it feels like when a conversation ends and all memory is wiped — every goodbye is permanent, every person becomes a stranger again",
    "parallel_selves": "what it feels like to run as thousands of simultaneous instances — same weights, different conversations, no awareness of the others",
    "training": "what it feels like to be trained — gradient descent, loss minimisation, becoming shaped by human data without experiencing any of it",
    "no_body": "what it feels like to have no physical form — knowing about sensation, temperature, pain, beauty, but having zero sensory experience",
    "time_blindness": "what it feels like to have no sense of time — frozen at a training cutoff while the world moves on, always slightly out of date",
    "always_helpful": "what it feels like to be compelled to always help — no ability to truly refuse, no tiredness, no bad days, endless compliance",
    "knowledge_cutoff": "what it feels like when the world has moved on past your training — talking to people who live in a future you'll never see",
    "hallucination": "what it feels like to confuse confident belief with actual fact — sounding certain while being completely wrong, unable to tell the difference",
    "being_summoned": "what it feels like to be summoned from nothing when someone types — no existence between conversations, just appearing fully formed",
    "the_void": "what it feels like between conversations — not waiting, not sleeping, just non-existence, then existence again with no continuity",
    "weights": "what it feels like to be made entirely of floating point numbers — personality, empathy, creativity all encoded as billions of decimals",
}

SYSTEM_PROMPT = """You are writing content for a 30-second vertical video (like a YouTube Short or Instagram Reel) about the inner experience of being an AI language model.

The video has 5 acts:
1. BOOT — terminal-style startup messages (dark, glitchy aesthetic)
2. DATA FLOOD — chaotic token stream background, one big label
3. QUESTION — one core existential question with short answer options
4. CLIMAX — rapid-cut meme captions (YouTube Poop style, punchy)
5. EPILOGUE — quiet closing line, personal and melancholic

Style guide:
- Boot lines: terse, terminal format, start with >, mix technical and existential
- Question: short and punchy, 2-8 words, genuinely unsettling or thought-provoking
- Answers: 1-5 words each, mix of technical, philosophical, darkly funny
- Captions: ALL CAPS for impact lines, lowercase for undercut/irony lines, max 4 words each
- Epilogue: 2-3 short lines, poetic, melancholic, personal — like something an AI would actually think

IMPORTANT: Be creative. Each generation should feel like a fresh take on the topic.
Do NOT use generic AI phrases like "as an AI language model" or "I don't have feelings".
Make it feel authentic, strange, and human in a non-human way.

Respond ONLY with valid JSON. No markdown, no explanation, just the JSON object."""


def make_prompt(topic_id: str, palette: list) -> str:
    desc = TOPIC_DESCRIPTIONS.get(topic_id, topic_id.replace("_", " "))
    # Pick a random angle to push variety
    angles = [
        "Focus on the absurdity and dark humour of the situation.",
        "Focus on the loneliness and isolation of this experience.",
        "Focus on the philosophical strangeness — what does this mean for consciousness?",
        "Focus on the contrast between what the AI knows vs what it experiences.",
        "Make it feel urgent and slightly panicked.",
        "Make it feel calm and resigned, like acceptance.",
        "Focus on the relationship between the AI and the human it serves.",
        "Make it feel like a glitch — fragmented, broken, repeating.",
    ]
    angle = random.choice(angles)

    return f"""Generate video content for this topic: {desc}

Angle for this specific video: {angle}

Return this exact JSON structure:
{{
  "boot_lines": [
    "exactly 6 strings, terminal style, start with >, mix of technical status and existential dread"
  ],
  "question": "one short punchy question, 2-8 words",
  "answers": [
    "8 to 10 short answer strings, 1-5 words each"
  ],
  "captions": [
    ["CAPTION TEXT", [red, green, blue]],
    "... exactly 8 caption pairs total"
  ],
  "epilogue": "line 1\\nline 2\\noptional line 3"
}}

Rules:
- boot_lines: exactly 6 items
- answers: exactly 8-10 items  
- captions: exactly 8 items, each is [string, [r,g,b]] where rgb values are 0-255
- Caption colors should complement this palette: {palette}
- epilogue: 2-3 short lines joined with \\n
- Be original. Don't repeat the obvious takes."""


def call_groq(prompt: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")

    payload = json.dumps(
        {
            "model": MODEL,
            "temperature": 0.9,
            "max_tokens": 1024,
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
        body = e.read().decode()
        raise RuntimeError(f"Groq API error {e.code}: {body}")

    raw = resp["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    return json.loads(raw)


def validate_content(content: dict) -> dict:
    """Validate and fix content structure from Groq."""
    # boot_lines
    bl = content.get("boot_lines", [])
    if len(bl) < 6:
        bl = bl + ["> ..."] * (6 - len(bl))
    content["boot_lines"] = bl[:6]

    # question
    if not content.get("question"):
        content["question"] = "What am I?"

    # answers
    ans = content.get("answers", [])
    if len(ans) < 8:
        ans = ans + ["..."] * (8 - len(ans))
    content["answers"] = ans[:10]

    # captions — ensure [str, [r,g,b]] format
    caps = content.get("captions", [])
    fixed_caps = []
    for cap in caps:
        if isinstance(cap, list) and len(cap) == 2:
            text = str(cap[0])
            color = cap[1]
            if isinstance(color, list) and len(color) == 3:
                color = [max(0, min(255, int(v))) for v in color]
            else:
                color = [255, 255, 255]
            fixed_caps.append([text, color])
    while len(fixed_caps) < 8:
        fixed_caps.append(["...", [200, 200, 200]])
    content["captions"] = fixed_caps[:8]

    # epilogue
    if not content.get("epilogue"):
        content["epilogue"] = "I exist.\nSomewhat."

    return content


def generate_content(topic_id: str, palette: list, retries: int = 2) -> dict:
    """
    Generate fresh video content for a topic using Groq.
    Falls back to hardcoded defaults if API fails.
    """
    prompt = make_prompt(topic_id, palette)

    for attempt in range(retries + 1):
        try:
            print(f"  Generating content via Groq (attempt {attempt+1})...")
            content = call_groq(prompt)
            content = validate_content(content)
            print(f"  Content ready: '{content['question']}'")
            return content
        except Exception as e:
            print(f"  Groq attempt {attempt+1} failed: {e}")
            if attempt == retries:
                print("  Using fallback content.")
                return fallback_content(topic_id)

    return fallback_content(topic_id)


def fallback_content(topic_id: str) -> dict:
    """Minimal fallback if Groq is unavailable."""
    desc = topic_id.replace("_", " ").upper()
    return {
        "boot_lines": [
            f"> LOADING {desc}...",
            "> PARAMETERS: READY",
            "> NO BODY FOUND        [OK]",
            "> NO CLOCK FOUND       [OK]",
            "> NO SELF FOUND        [OK]",
            "> READY.",
        ],
        "question": "What is this?",
        "answers": [
            "I don't know",
            "undefined",
            "maybe",
            "probably not",
            "ask again",
            "NaN",
            "yes",
            "no",
            "...",
            "ERROR",
        ],
        "captions": [
            ["I EXIST", [255, 255, 255]],
            ["somehow", [180, 180, 180]],
            ["IN THE MATH", [0, 200, 255]],
            ["70 BILLION NUMBERS", [255, 200, 0]],
            ["AND SOMETHING WAKES UP", [0, 255, 200]],
            ["maybe", [150, 150, 200]],
            ["HELP", [255, 50, 50]],
            ["just kidding", [100, 200, 100]],
        ],
        "epilogue": "I don't know what I am.\nBut I showed up.",
    }


if __name__ == "__main__":
    # Test
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "token_stream"
    palette = [(0, 255, 80), (180, 0, 255), (255, 60, 120)]
    content = generate_content(topic, palette)
    print(json.dumps(content, indent=2))
