#!/usr/bin/env python3
"""
Triggered by delete.yml (Reject button).
Just sends a confirmation — artifact expires automatically.
Nothing was uploaded to YouTube so nothing to delete there.
"""

import os, sys, hmac, hashlib, smtplib, ssl


def verify(run_id: str, sig: str) -> bool:
    secret   = os.environ.get("PIPELINE_SECRET", "change-me")
    expected = hmac.new(secret.encode(), run_id.encode(), hashlib.sha256).hexdigest()[:24]
    return hmac.compare_digest(expected, sig)


def send_confirm():
    gmail  = os.environ.get("GMAIL_ADDRESS", "")
    passwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    notify = os.environ.get("NOTIFY_EMAIL", gmail)
    run_id = os.environ.get("RUN_ID", "")
    if not gmail or not passwd:
        return
    html = f"""<html><body style="font-family:Arial;background:#111;color:#ddd;padding:30px">
<h2 style="color:#d63031">🗑 Video Rejected</h2>
<p>Run <code>{run_id}</code> was rejected. No video was uploaded to YouTube.</p>
</body></html>"""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[LLM Shorts] Video Rejected"
    msg["From"]    = gmail
    msg["To"]      = notify
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(gmail, passwd)
        s.sendmail(gmail, notify, msg.as_string())
    print("  ✓ Rejection confirmed via email")


run_id = os.environ.get("RUN_ID", "")
sig    = os.environ.get("SIG", "")

if not verify(run_id, sig):
    print("❌ Invalid signature."); sys.exit(1)

print(f"🗑 Rejected run {run_id}. No YouTube upload was made.")
send_confirm()
