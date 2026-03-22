#!/usr/bin/env python3
"""
One-time OAuth2 helper — run locally to get your YouTube refresh token.
Uses localhost redirect (replaces the blocked OOB flow).

Steps:
1. Google Cloud Console → APIs & Services → Enable "YouTube Data API v3"
2. OAuth consent screen → Publish App (so token never expires)
3. Credentials → edit your OAuth 2.0 Desktop client
   → add http://localhost:8080 to Authorized redirect URIs → Save
4. Run: python3 scripts/auth.py
5. Browser opens automatically — sign in and approve
6. Terminal prints YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
7. Add all three to GitHub → Settings → Secrets and variables → Actions
"""

import urllib.request, urllib.parse, json, sys, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

CLIENT_ID     = input("Paste your client_id: ").strip()
CLIENT_SECRET = input("Paste your client_secret: ").strip()
SCOPE         = "https://www.googleapis.com/auth/youtube.upload"
REDIRECT_URI  = "http://localhost:8080"

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

captured_code = []

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            captured_code.append(params["code"][0])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code received.")

    def log_message(self, *args):
        pass  # silence request logs


server = HTTPServer(("localhost", 8080), Handler)
print("\n→ Opening browser for authorization...")
webbrowser.open(auth_url)
print("  Waiting for Google to redirect back to localhost:8080 ...\n")
while not captured_code:
    server.handle_request()
server.server_close()

code = captured_code[0]

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
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
try:
    with urllib.request.urlopen(req) as r:
        tokens = json.loads(r.read())
except urllib.error.HTTPError as e:
    print(f"❌ Token exchange failed HTTP {e.code}: {e.read().decode()}")
    sys.exit(1)

print("✅ Success!")
print(f"\nYOUTUBE_CLIENT_ID={CLIENT_ID}")
print(f"YOUTUBE_CLIENT_SECRET={CLIENT_SECRET}")
print(f"YOUTUBE_REFRESH_TOKEN={tokens['refresh_token']}")
print("\nAdd these three to GitHub → Settings → Secrets and variables → Actions")
