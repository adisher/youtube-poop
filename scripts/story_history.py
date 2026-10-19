#!/usr/bin/env python3
"""
Story history — remembers which stories were already told so new ones never repeat.

Persists story_history.json on the gh-pages branch via the GitHub Contents API
(same approach as remnant.py, so GH_PAT needs no extra permissions).

Public API used by pipeline.py:
  load(pat, repo)                 -> (entries, sha)
  save(entries, sha, pat, repo)
  add(entries, kit)               -> entries with the new story appended
"""

import json, base64, urllib.request, urllib.error
from datetime import datetime, timezone

_PATH      = "story_history.json"
_GH_BRANCH = "gh-pages"
_KEEP      = 120   # ~40 days at 3 videos/day


def _headers(pat: str) -> dict:
    return {
        "Authorization":        f"token {pat}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":         "application/json",
    }


def load(pat: str, repo: str) -> tuple:
    """Return (entries, sha). Missing file -> ([], None). Network errors -> ([], None)."""
    url = f"https://api.github.com/repos/{repo}/contents/{_PATH}?ref={_GH_BRANCH}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_headers(pat)), timeout=30) as r:
            data = json.loads(r.read())
            entries = json.loads(base64.b64decode(data["content"]).decode())
            return (entries if isinstance(entries, list) else []), data["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"[HISTORY] GET failed (HTTP {e.code}) — continuing without history")
        return [], None
    except Exception as e:
        print(f"[HISTORY] GET failed ({e}) — continuing without history")
        return [], None


def add(entries: list, kit: dict) -> list:
    entries = entries + [{
        "date":    datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "slot":    kit.get("slot", ""),
        "genre":   kit.get("genre", ""),
        "title":   kit.get("title", ""),
        "premise": kit.get("premise", ""),
    }]
    return entries[-_KEEP:]


def save(entries: list, sha: str | None, pat: str, repo: str) -> None:
    """Write history back. Failures are logged, never fatal — the video is already out."""
    body = {
        "message": "chore: story history update",
        "content": base64.b64encode(json.dumps(entries, indent=2).encode()).decode(),
        "branch":  _GH_BRANCH,
    }
    url = f"https://api.github.com/repos/{repo}/contents/{_PATH}"
    for attempt in range(2):
        if sha:
            body["sha"] = sha
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PUT",
                                     headers=_headers(pat))
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            print(f"[HISTORY] Saved — {len(entries)} stories remembered")
            return
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt == 0:
                # Another run wrote in between: refetch its SHA and retry once
                _, sha = load(pat, repo)
                continue
            print(f"[HISTORY] PUT failed (HTTP {e.code}): {e.read().decode()[:200]}")
            return
        except Exception as e:
            print(f"[HISTORY] PUT failed ({e})")
            return
