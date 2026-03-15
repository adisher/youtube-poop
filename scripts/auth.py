#!/usr/bin/env python3
"""
One-time OAuth2 helper — run locally to get your YouTube refresh token.
After running this once, put YOUTUBE_REFRESH_TOKEN in your environment/secrets.

Steps:
1. Go to https://console.cloud.google.com/
2. Create a project → Enable "YouTube Data API v3"
3. OAuth consent screen → add yourself as test user
4. Credentials → Create OAuth 2.0 Client ID → Desktop App
5. Download client_secret.json or paste client_id + secret below
6. Run: python3 auth.py
7. Open the URL, approve, paste the code back
8. Copy the refresh_token — add it to your env as YOUTUBE_REFRESH_TOKEN
"""

import urllib.request, urllib.parse, json, sys

CLIENT_ID     = input("Paste your client_id: ").strip()
CLIENT_SECRET = input("Paste your client_secret: ").strip()
SCOPE         = "https://www.googleapis.com/auth/youtube.upload"
REDIRECT_URI  = "urn:ietf:wg:oauth:2.0:oob"   # desktop / copy-paste flow

auth_url = (
    "https://accounts.google.com/o/oauth2/auth?"
    + urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
    })
)

print(f"\n→ Open this URL in your browser:\n\n{auth_url}\n")
code = input("Paste the authorization code here: ").strip()

payload = urllib.parse.urlencode({
    "code":          code,
    "client_id":     CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri":  REDIRECT_URI,
    "grant_type":    "authorization_code",
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=payload,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)
with urllib.request.urlopen(req) as r:
    tokens = json.loads(r.read())

print("\n✅ Success!")
print(f"\nYOUTUBE_CLIENT_ID={CLIENT_ID}")
print(f"YOUTUBE_CLIENT_SECRET={CLIENT_SECRET}")
print(f"YOUTUBE_REFRESH_TOKEN={tokens['refresh_token']}")
print("\nAdd these to your .env file or GitHub Actions secrets.")
