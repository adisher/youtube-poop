#!/usr/bin/env python3
"""
content_gen.py
Calls OpenRouter to invent a brand-new original short story AND all the
on-screen content for it. Every run = a different creative story.

Freshness comes from three layers:
  1. A genre that rotates by date + slot, so every day (and every slot in a day)
     gets a different kind of story.
  2. Random "sparks" (hero, place, object, twist) combined per run.
  3. A history of recent stories passed to the LLM as "do not repeat", plus a
     duplicate-title check that rerolls the story if it matches a recent one.

Required env var: OPENROUTER_API_KEY
"""

import os, json, random, time, re, urllib.request, urllib.error
from datetime import datetime, timezone

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"

# Preferred free models, tried first when OpenRouter still lists them as free.
# Free models get delisted or turn paid often, so the live free list from
# MODELS_URL is appended at runtime (see candidate_models).
MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "arcee-ai/trinity-large-preview:free",
    "stepfun/step-3.5-flash:free",
]
FREE_ROUTER = "openrouter/free"   # OpenRouter's own router across free models
MAX_ATTEMPTS = 6

# Rotates by date + slot. 16 genres and 3 slots share no common factor, so
# consecutive runs walk through every genre before any repeats.
GENRES = [
    "heartwarming slice of life",
    "whimsical fantasy fable",
    "hopeful science fiction",
    "cozy mystery with a clever reveal",
    "absurd comedy",
    "epic adventure in miniature",
    "magical realism",
    "folktale retold in a modern city",
    "underdog triumph",
    "sweet, gentle love story",
    "space exploration wonder",
    "time travel with a kind twist",
    "talking animal tale",
    "inventor's breakthrough",
    "unlikely friendship",
    "bedtime-story myth about how something came to be",
]

SLOT_INDEX = {"morning": 0, "afternoon": 1, "evening": 2}

HEROES = [
    "a retired lighthouse keeper", "a girl who repairs broken clocks", "a robot gardener",
    "a street violinist", "a nervous dragon", "a grandmother learning to skateboard",
    "a delivery drone that got lost", "a baker who works only at night",
    "a boy who collects lost socks", "a cloud that wants to be a mountain",
    "a librarian on the moon", "a stray cat with a map", "a shy astronaut",
    "a snowman who refuses to melt", "a tired superhero on vacation",
    "a mapmaker who has never left home", "an old ferry captain", "a tiny knight",
    "a school janitor with a secret", "a paper airplane", "a twin who lost a bet",
    "a fox who runs a bookshop", "an inventor's forgotten prototype", "a kite maker",
]

PLACES = [
    "a floating market", "a train that never stops", "a village inside a whale",
    "a rooftop garden in a megacity", "the last bus stop on Earth", "a desert of glass",
    "an island that moves every night", "a hospital for broken toys", "an underwater post office",
    "a bakery at the edge of the universe", "a small town where it always snows on Tuesdays",
    "a city built on giant turtles", "a forest where the trees hum", "a laundromat at 2am",
    "a mountain observatory", "a school for future weather", "a junkyard full of stars",
]

OBJECTS = [
    "a jar of bottled sunlight", "a compass that points to what you need",
    "a recipe missing one ingredient", "an umbrella that controls rain",
    "a letter addressed to the future", "a key with no door", "a tiny seed that glows",
    "a broken music box", "a camera that photographs dreams", "a ticket for a train that left yesterday",
    "a pencil that can't erase", "a map drawn by a child", "a bell nobody can ring",
    "a pair of mismatched wings", "a clock that runs backwards",
]

TWISTS = [
    "the helper was the hero all along", "the treasure was a memory",
    "the problem solves itself in a funny way", "the villain just wanted a friend",
    "the small choice changes everything", "the ending loops back to the first line",
    "the quest was a gift for someone else", "the hero teaches the teacher",
    "the impossible thing turns out to be simple", "the wish comes true sideways",
    "the stranger is family", "the last line reveals who has been telling the story",
]

SYSTEM_PROMPT = """You write original micro-stories for 30-second vertical short videos (YouTube Shorts / Reels).

Each video tells ONE complete, creative story with a beginning, a turn, a climax and an ending.
There is no narrator — the story is told entirely through on-screen text, so every line must be short and vivid.
Tone: imaginative, warm, surprising, funny or uplifting. Original characters and worlds.
NOT horror. No ghosts, gore, death, creepy entities, jump scares or dread.

The video has 5 acts:
1. OPENING — exactly 4 short lines that introduce the hero, the world and what they want
2. SPARK — a stream of 10 story keywords (single words) flowing past the screen
3. QUESTION — the story's turning point as one question, with 8-10 possible answers flashing by
4. CLIMAX — 8 punchy captions that tell the climax beat by beat (ALL CAPS for big moments, lowercase for jokes and quiet asides)
5. ENDING — 2-3 short lines that land the story with a twist, a smile or a lump in the throat

Style rules:
- Opening lines: max 38 characters each, plain storytelling sentences (e.g. "Pip fixed clocks for a living.")
- Keywords: single words, max 12 characters, nouns or verbs from the story
- Question: 3-8 words, specific to this story (e.g. "What would Pip trade for time?")
- Answers: 1-4 words each, playful possibilities, wrong guesses and the real one
- Captions: max 5 words each, must read as a sequence that tells the climax
- Ending: max 34 characters per line, satisfying and complete
- card_lines: exactly 3 lines for a mid-climax title card, like a storybook page:
  [one big word or short phrase (max 14 chars), a short line, a short line]
  (e.g. ["MEANWHILE...", "the clock stopped", "and Pip started running"])
- YouTube title: plain English, curiosity-driven, max 8 words
  (e.g. "The Girl Who Fixed Time", "Grandpa's Last Invention", "The Moon Forgot To Rise")

Also choose a visual style that matches the story's mood:
- boot_style (falling symbols in act 1): "stars" | "notes" | "petals" | "hearts" | "snow" | "weather" | "blocks" | "binary" | "katakana"
- flood_style (act 2 color): "green" | "cyan" | "purple" | "amber" | "red" | "pink" | "gold"
- question_bg: "hue_shift" | "grid" | "waveform" | "particles" | "static" | "vhs_static"
- climax_speed: "slow" | "medium" | "fast"
- climax_style: "corrupt" | "digital" | "void" | "warm"
  corrupt = loud YTP-style noise and colour blocks (good for comedy)
  digital = scan lines, grid pulses, scrolling streams (good for sci-fi)
  void = deep space particles, radial glow (good for wonder and myth)
  warm = soft glowing light orbs and gentle gradients (good for heartfelt stories)
- epilogue_color: "white" | "green" | "cyan" | "amber" | "pink"
- palette: 3 RGB colors that match the mood. Rich and expressive — bright accents are welcome.

Respond ONLY with valid JSON. No markdown fences. No explanation."""


def genre_for(slot: str, when: datetime | None = None) -> str:
    """Pick today's genre for this slot. Changes every day and every slot."""
    when = when or datetime.now(timezone.utc)
    idx = when.date().toordinal() * len(SLOT_INDEX) + SLOT_INDEX.get(slot, 0)
    return GENRES[idx % len(GENRES)]


def make_sparks() -> dict:
    return {
        "hero": random.choice(HEROES),
        "place": random.choice(PLACES),
        "object": random.choice(OBJECTS),
        "twist": random.choice(TWISTS),
    }


def make_prompt(genre: str, sparks: dict, recent: list | None = None,
                epilogue_extra: str | None = None) -> str:
    base = f"""Write a brand-new original micro-story for today's short video.

Genre: {genre}

Creative sparks (use at least two of them, transform them freely):
- Hero: {sparks['hero']}
- Place: {sparks['place']}
- Object: {sparks['object']}
- Twist idea: {sparks['twist']}
"""
    if recent:
        listed = "\n".join(
            f"- {r.get('title', '')}: {r.get('premise', '')}".rstrip(": ")
            for r in recent[-25:]
        )
        base += f"""
These stories were already told. Do NOT repeat their titles, heroes or premises:
{listed}
"""
    base += """
Return this exact JSON:
{
  "title": "curiosity-driven title, max 8 words",
  "topic_id": "snake_case_identifier",
  "genre": "the genre above",
  "premise": "one sentence summary of the whole story",
  "palette": [[r,g,b], [r,g,b], [r,g,b]],
  "boot_style": "stars|notes|petals|hearts|snow|weather|blocks|binary|katakana",
  "flood_style": "green|cyan|purple|amber|red|pink|gold",
  "question_bg": "hue_shift|grid|waveform|particles|static|vhs_static",
  "climax_speed": "slow|medium|fast",
  "climax_style": "corrupt|digital|void|warm",
  "epilogue_color": "white|green|cyan|amber|pink",
  "boot_lines": ["exactly 4 opening lines, max 38 chars each"],
  "keywords": ["10 single-word story keywords"],
  "question": "3-8 word turning-point question",
  "answers": ["8 to 10 short answers, 1-4 words each"],
  "captions": [["CAPTION", [r,g,b]], "... 8 total, telling the climax in order"],
  "card_lines": ["BIG PHRASE", "short line", "short line"],
  "epilogue": "line1\\nline2\\noptional line3"
}"""
    if epilogue_extra:
        base += f"\n\nEnding instruction: {epilogue_extra}"
    return base


def call_llm(prompt: str, model: str) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    payload = json.dumps(
        {
            "model": model,
            "temperature": 1.0,
            "max_tokens": 1400,
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
        with urllib.request.urlopen(req, timeout=60) as r:
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
    # Keep only the JSON object — drops markdown fences and any prose around it
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError(f"No JSON object in response: {raw[:120]!r}")
    return json.loads(raw[start:end + 1])


def candidate_models() -> list:
    """Preferred models that are still free, then the newest other free models."""
    try:
        with urllib.request.urlopen(MODELS_URL, timeout=20) as r:
            data = json.loads(r.read())["data"]
    except Exception as e:
        print(f"  Could not list OpenRouter models ({e}) — using built-in list")
        return MODELS + [FREE_ROUTER]

    def is_free_text(m):
        pricing = m.get("pricing") or {}
        modality = (m.get("architecture") or {}).get("modality", "text->text")
        return (
            m.get("id", "").endswith(":free")
            and str(pricing.get("prompt", "0")) in ("0", "0.0")
            and str(pricing.get("completion", "0")) in ("0", "0.0")
            and modality.endswith("->text")
            and (m.get("context_length") or 0) >= 8000
        )

    free = sorted((m for m in data if is_free_text(m)),
                  key=lambda m: m.get("created", 0), reverse=True)
    free_ids = [m["id"] for m in free]
    ordered = [m for m in MODELS if m in free_ids] + [m for m in free_ids if m not in MODELS]
    picked = ordered[:MAX_ATTEMPTS - 1] + [FREE_ROUTER]
    print(f"  {len(free_ids)} free models listed — trying: {', '.join(picked)}")
    return picked


def _pick(content: dict, key: str, allowed: tuple, default: str) -> str:
    return content.get(key) if content.get(key) in allowed else default


def validate(content: dict) -> dict:
    """Ensure all required fields exist and have correct types."""
    if not content.get("title"):
        raise ValueError("story has no title")
    content["title"] = str(content["title"]).strip()[:90]

    if not content.get("topic_id"):
        content["topic_id"] = re.sub(r"[^a-z0-9]+", "_", content["title"].lower()).strip("_") or "story"
    content["premise"] = str(content.get("premise", "")).strip()[:240]

    # palette — 3 rgb triples
    pal = content.get("palette", [])
    if not isinstance(pal, list):
        pal = []
    pal = [p for p in pal if isinstance(p, list) and len(p) == 3]
    while len(pal) < 3:
        pal.append(
            [random.randint(120, 255), random.randint(80, 220), random.randint(80, 255)]
        )
    content["palette"] = [[max(0, min(255, int(v))) for v in p] for p in pal[:3]]

    # visual style choices
    content["boot_style"] = _pick(
        content, "boot_style",
        ("stars", "notes", "petals", "hearts", "snow", "weather", "blocks", "binary", "katakana"),
        "stars",
    )
    content["flood_style"] = _pick(
        content, "flood_style", ("green", "cyan", "purple", "amber", "red", "pink", "gold"), "gold"
    )
    content["question_bg"] = _pick(
        content, "question_bg",
        ("hue_shift", "grid", "waveform", "particles", "static", "vhs_static"),
        "particles",
    )
    content["climax_speed"] = _pick(content, "climax_speed", ("slow", "medium", "fast"), "medium")
    content["climax_style"] = _pick(
        content, "climax_style", ("corrupt", "digital", "void", "warm"), "warm"
    )
    content["epilogue_color"] = _pick(
        content, "epilogue_color", ("white", "green", "cyan", "amber", "pink"), "white"
    )

    # opening lines
    bl = [str(x) for x in content.get("boot_lines", []) if str(x).strip()]
    if len(bl) < 3:
        raise ValueError("story has fewer than 3 opening lines")
    content["boot_lines"] = _wrap(bl[:4], 40)[:7]

    # keywords
    kw = [str(x).strip()[:14] for x in content.get("keywords", []) if str(x).strip()]
    if len(kw) < 4:
        kw += content["title"].split()
    content["keywords"] = kw[:12]

    if not content.get("question"):
        raise ValueError("story has no question")

    ans = [str(x) for x in content.get("answers", []) if str(x).strip()]
    if len(ans) < 4:
        raise ValueError("story has fewer than 4 answers")
    content["answers"] = ans[:10]

    # captions
    fixed = []
    for cap in content.get("captions", []):
        if isinstance(cap, list) and len(cap) == 2:
            color = (
                cap[1]
                if isinstance(cap[1], list) and len(cap[1]) == 3
                else [255, 255, 255]
            )
            fixed.append([str(cap[0]), [max(0, min(255, int(v))) for v in color]])
        elif isinstance(cap, str) and cap.strip():
            fixed.append([cap, [255, 255, 255]])
    if len(fixed) < 4:
        raise ValueError("story has fewer than 4 captions")
    content["captions"] = fixed[:8]

    if not content.get("epilogue"):
        raise ValueError("story has no ending")

    # card_lines — 3 storybook title-card strings shown mid-climax
    cl = content.get("card_lines", [])
    if not isinstance(cl, list) or len(cl) < 3:
        cl = ["MEANWHILE...", content["question"], content["epilogue"].split("\n")[0]]
    content["card_lines"] = [str(x)[:60] for x in cl[:3]]

    return content


def _wrap(lines: list, width: int) -> list:
    """Split lines longer than width at word boundaries so they fit on screen."""
    out = []
    for line in lines:
        cur = ""
        for word in line.split():
            if cur and len(cur) + 1 + len(word) > width:
                out.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            out.append(cur)
    return out


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def is_repeat(content: dict, recent: list | None) -> bool:
    titles = {_norm(r.get("title", "")) for r in (recent or [])}
    return _norm(content["title"]) in titles


# ── Offline fallback ──────────────────────────────────────────────────────────
# Used only when every model fails. Builds a story from the spark lists so even
# fallback videos differ run to run instead of cycling a few fixed scripts.

_FALLBACK_STYLES = [
    ("stars", "gold", "particles", "void", "amber", [[255, 200, 90], [70, 60, 160], [255, 140, 180]]),
    ("petals", "pink", "hue_shift", "warm", "pink", [[255, 150, 190], [120, 70, 150], [255, 220, 140]]),
    ("notes", "cyan", "waveform", "digital", "cyan", [[80, 220, 255], [40, 60, 140], [255, 240, 120]]),
    ("weather", "green", "grid", "corrupt", "green", [[120, 255, 140], [30, 90, 70], [255, 200, 60]]),
    ("snow", "purple", "particles", "warm", "white", [[200, 220, 255], [90, 60, 170], [255, 180, 220]]),
]


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _strip_article(s: str) -> str:
    return re.sub(r"^(a|an|the)\s+", "", s)


def fallback(genre: str, sparks: dict, recent: list | None = None) -> dict:
    for _ in range(20):
        hero, place, obj = sparks["hero"], sparks["place"], sparks["object"]
        hero_short = _strip_article(hero)
        obj_short = _strip_article(obj)
        title = random.choice([
            f"The {hero_short} and the {obj_short}",
            f"How {hero} saved {place}",
            f"The day {hero} found {obj}",
        ])
        title = " ".join(w[:1].upper() + w[1:] for w in title.split())
        if not is_repeat({"title": title}, recent):
            break
        sparks = make_sparks()
    boot, flood, qbg, cstyle, ecolor, palette = random.choice(_FALLBACK_STYLES)
    words = [w for w in re.findall(r"[a-zA-Z]+", f"{hero} {place} {obj}") if len(w) > 3]
    return validate({
        "title": title[:90],
        "topic_id": re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_"),
        "genre": genre,
        "premise": f"{_cap(hero)} in {place} discovers {obj}, and {sparks['twist']}.",
        "palette": palette,
        "boot_style": boot,
        "flood_style": flood,
        "question_bg": qbg,
        "climax_speed": "medium",
        "climax_style": cstyle,
        "epilogue_color": ecolor,
        "boot_lines": [
            f"Once there was {hero}.",
            f"They lived in {place}.",
            "Every day felt the same.",
            f"Until they found {obj}.",
        ],
        "keywords": list(dict.fromkeys(w.lower() for w in words))[:10] or ["story"],
        "question": f"What would {hero_short} do next?",
        "answers": ["run away", "keep it secret", "ask for help", "make a wish",
                    "share it", "follow it", "laugh", "be brave"],
        "captions": [
            ["IT STARTED SMALL", [255, 230, 120]],
            ["then it grew", [200, 200, 255]],
            ["EVERYONE NOTICED", [255, 140, 140]],
            ["nobody expected this", [180, 180, 180]],
            ["ONE BRAVE CHOICE", [120, 255, 160]],
            ["and a little luck", [200, 200, 200]],
            ["EVERYTHING CHANGED", [255, 200, 90]],
            ["for the better", [255, 255, 255]],
        ],
        "card_lines": ["MEANWHILE...", f"in {place}", "something wonderful began"],
        "epilogue": f"In the end,\n{sparks['twist']}.\nAnd everyone smiled.",
    })


def generate_topic(epilogue_extra: str | None = None, *, slot: str = "morning",
                   recent: list | None = None) -> dict:
    """Generate a completely fresh story and all content via OpenRouter."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    print(f"  OPENROUTER_API_KEY: {'SET (' + key[:8] + '...)' if key else 'NOT SET'}")
    genre = genre_for(slot)
    print(f"  Genre today ({slot}): {genre}")
    sparks = make_sparks()
    models = candidate_models()
    for i, model in enumerate(models):
        try:
            print(f"  Generating story (model: {model})...")
            content = validate(call_llm(make_prompt(genre, sparks, recent, epilogue_extra), model))
            if is_repeat(content, recent):
                raise ValueError(f"title '{content['title']}' was already used")
            content["genre"] = genre
            print(f"  Story: '{content['title']}'")
            print(f"  Premise: {content['premise']}")
            return content
        except Exception as e:
            print(f"  {model} failed: {e}")
            sparks = make_sparks()  # reroll sparks so the next attempt differs
            if i < len(models) - 1:
                print("  Waiting 5s before trying next model...")
                time.sleep(5)
    print("  All models failed. Using procedural fallback story.")
    return fallback(genre, sparks, recent)


if __name__ == "__main__":
    import sys

    content = generate_topic(slot=sys.argv[1] if len(sys.argv) > 1 else "morning")
    print(json.dumps(content, indent=2))
