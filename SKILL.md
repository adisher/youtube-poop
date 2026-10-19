---
name: llm-shorts
description: Generate a vertical (Reel/Short) video that tells a brand-new original micro-story, paired with a YouTube kit (title, description). Use this skill when the user wants to: generate a story short, create a YouTube short, make a new reel for the schedule, or run the daily video generation pipeline. Triggers on phrases like "generate video", "make a short", "run the pipeline", "new reel", "daily video", "story short".
---

# LLM Shorts — Skill

Generates a vertical 9:16 short-form video (1080×1920, 30s) that tells **one complete, original creative story** (fantasy, sci-fi, comedy, cozy mystery, heartwarming and more — never horror). Visuals and audio are rendered with **only Python + ffmpeg**; the story itself is written by a free OpenRouter LLM. Each run produces:

1. `output/video.mp4` — the rendered Reel/Short
2. `output/kit.json` — `{ title, description, genre, premise, topic, slot, scheduled_time_utc, video }`

YouTube selects its own thumbnail for Shorts/Reels — no thumbnail is generated.

---

## How every story stays new

- **Genre rotates by date and slot** (16 genres, 3 slots a day), so each day's three videos are different kinds of story and the mix changes daily.
- **Random sparks** (hero, place, object, twist) are combined each run.
- **Story history** (`story_history.json` on the `gh-pages` branch, last 120 stories) is sent to the LLM as "do not repeat", and a story whose title matches a recent one is rejected and rewritten.
- If every model fails, a **procedural fallback** builds a story from the spark lists, so fallbacks differ too.

## Video structure (5 acts)

| Act | Length | Content |
|---|---|---|
| Opening | 5s | 4 short lines introducing the hero, world and goal, over falling symbols (stars, notes, petals, hearts, snow, weather) |
| Spark | 5s | Story keywords streaming past |
| Question | 6s | The turning point as a question, with possible answers flashing by |
| Climax | 8s | 8 captions telling the climax, plus a storybook title card |
| Ending | 6s | 2–3 lines that land the story |

## File Structure

```
llm-shorts/                          ← install this whole folder
├── SKILL.md
├── .env.example                     ← copy to .env, fill in secrets
├── scripts/
│   ├── content_gen.py               ← story writer (OpenRouter LLM + fallback)
│   ├── story_history.py             ← remembers past stories (no repeats)
│   ├── generate.py                  ← video renderer (Python + ffmpeg)
│   ├── pipeline.py                  ← orchestrator: generate → upload → email
│   ├── publish.py                   ← triggered by approve button
│   ├── delete.py                    ← triggered by reject button
│   ├── upload.py                    ← YouTube Data API v3 uploader
│   └── auth.py                      ← one-time OAuth2 token helper (run locally)
└── .github/workflows/
    ├── pipeline.yml                 ← cron: 8:05 AM, 1:05 PM, 6:05 PM ET daily
    ├── publish.yml                  ← workflow_dispatch: approve action
    └── delete.yml                   ← workflow_dispatch: reject action
```

Push this entire folder as a **private GitHub repository**.

---

## How to invoke this skill

When the user asks to generate a video, run:

```bash
python3 scripts/generate.py [--slot morning|afternoon|evening]
```

Or to run the full pipeline (generate + upload + email):

```bash
python3 scripts/pipeline.py [--slot morning|afternoon|evening]
```

---

## Automation Flow (fully serverless, private repo)

```
GitHub Actions cron (8:05 AM / 1:05 PM / 6:05 PM ET)
  → pipeline.py runs
  → video generated
  → uploaded to YouTube as PRIVATE
  → approval email sent with review.html attached

You open email
  → click YouTube link to preview (private)
  → open review.html attachment in browser
  → click Approve or Reject
  → GitHub Actions API called directly from browser
  → publish.yml or delete.yml fires
  → video goes public (or deleted)
  → confirmation email sent
```

No server. No VPS. No always-on machine. Works on phone.

---

## Genres

Stories rotate through the `GENRES` list in `scripts/content_gen.py`. Add genres or sparks (`HEROES`, `PLACES`, `OBJECTS`, `TWISTS`) there to widen the variety.

The old REMNANT horror ARG layer (`scripts/remnant.py`) is off by default. Set the env var `REMNANT_ENABLED=1` in the workflow to turn it back on.

---

## One-Time Setup

**1. Create private GitHub repo**, push this folder as root.

**2. Get YouTube refresh token** (run once locally):
```bash
pip install Pillow numpy
python3 scripts/auth.py
```

**3. Add GitHub Secrets** (repo → Settings → Secrets → Actions):

| Secret | Source |
|---|---|
| `YOUTUBE_CLIENT_ID` | Google Cloud Console |
| `YOUTUBE_CLIENT_SECRET` | Google Cloud Console |
| `YOUTUBE_REFRESH_TOKEN` | Output of `auth.py` |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | myaccount.google.com → Security → App passwords |
| `NOTIFY_EMAIL` | Where to receive review emails |
| `GH_PAT` | GitHub → Settings → Developer settings → Fine-grained PAT (Actions: read+write) |
| `PIPELINE_SECRET` | `python3 -c "import secrets; print(secrets.token_hex(20))"` |
| `OPENROUTER_API_KEY` | openrouter.ai → Keys (free models are used) |

**4. Test manually**: Actions → Daily Pipeline → Run workflow.

---

## Scheduling

Three slots daily (UTC, see `.github/workflows/pipeline.yml`):
- **Morning** → 12:05 UTC
- **Afternoon** → 17:05 UTC
- **Evening** → 22:05 UTC

---

## YouTube Kit Format

`kit.json` schema:

```json
{
  "title": "The Girl Who Fixed Time",
  "description": "Pip, a girl who repairs clocks, ... \n\n#Storytime #ShortStory ...",
  "topic": "girl_fixed_time",
  "genre": "whimsical fantasy fable",
  "premise": "Pip, a girl who repairs clocks, ...",
  "slot": "morning",
  "scheduled_time_utc": "2026-10-20T12:31:00Z",
  "video": "/tmp/llm-shorts-morning-None/video.mp4"
}
```

Title: curiosity-driven, max 8 words. Description: one-line premise followed by hashtags.
