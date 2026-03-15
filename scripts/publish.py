#!/usr/bin/env python3
"""
Triggered by publish.yml (Approve button).
Downloads artifact, uploads to YouTube, sends confirmation email.
"""

import os, sys, json, hmac, hashlib, smtplib, ssl, zipfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import upload as up


def verify(run_id: str, sig: str) -> bool:
    secret   = os.environ.get("PIPELINE_SECRET", "change-me")
    expected = hmac.new(secret.encode(), run_id.encode(), hashlib.sha256).hexdigest()[:24]
    return hmac.compare_digest(expected, sig)


def send_confirm(title: str, video_id: str):
    gmail  = os.environ.get("GMAIL_ADDRESS", "")
    passwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    notify = os.environ.get("NOTIFY_EMAIL", gmail)
    if not gmail or not passwd:
        return
    yt  = f"https://www.youtube.com/watch?v={video_id}"
    html = f"""<html><body style="font-family:Arial;background:#111;color:#ddd;padding:30px">
<h2 style="color:#00b894">✅ Video Published</h2>
<p><b>{title}</b> is now live on YouTube.</p>
<p><a href="{yt}" style="color:#5865f2">{yt}</a></p>
</body></html>"""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[LLM Shorts] Published: {title}"
    msg["From"]    = gmail
    msg["To"]      = notify
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(gmail, passwd)
        s.sendmail(gmail, notify, msg.as_string())
    print(f"  ✓ Confirmation email sent")


run_id = os.environ.get("RUN_ID", "")
sig    = os.environ.get("SIG", "")

if not verify(run_id, sig):
    print("❌ Invalid signature."); sys.exit(1)

# Find kit.json in downloaded artifact
artifact_dir = Path("/tmp/artifact")
kit_files = list(artifact_dir.glob("**/kit.json"))
if not kit_files:
    print("❌ kit.json not found in artifact."); sys.exit(1)

with open(kit_files[0]) as f:
    kit = json.load(f)

# Find video file
video_files = list(artifact_dir.glob("**/*.mp4"))
if not video_files:
    print("❌ No mp4 found in artifact."); sys.exit(1)

video_path = str(video_files[0])
print(f"📤 Uploading: {kit['title']}")

token    = up.get_access_token()
video_id = up.upload_video(
    token, video_path,
    kit["title"], kit["description"],
    privacy="public",
)

if not video_id:
    print("❌ Upload failed."); sys.exit(1)

print(f"✅ Published: https://youtu.be/{video_id}")
send_confirm(kit["title"], video_id)
