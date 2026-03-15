#!/usr/bin/env python3
"""Triggered by Reject button — confirms rejection via email."""

import os, sys, hmac, hashlib, smtplib, ssl


def verify(run_id: str, sig: str) -> bool:
    secret = os.environ.get("PIPELINE_SECRET", "change-me")
    expected = hmac.new(secret.encode(), run_id.encode(), hashlib.sha256).hexdigest()[
        :24
    ]
    return hmac.compare_digest(expected, sig)


def send_confirm(run_id: str):
    gmail = os.environ.get("GMAIL_ADDRESS", "")
    passwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    notify = os.environ.get("NOTIFY_EMAIL", gmail)
    if not gmail or not passwd:
        return
    html = f"""<html><body style="font-family:Arial;background:#111;color:#ddd;padding:30px;max-width:500px">
<h2 style="color:#d63031">🗑 Rejected</h2>
<p>Run <code>{run_id}</code> was rejected. Nothing was uploaded to YouTube.</p>
</body></html>"""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[LLM Shorts] Video Rejected"
    msg["From"] = gmail
    msg["To"] = notify
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(gmail, passwd)
        s.sendmail(gmail, notify, msg.as_string())
    print("  ✓ Rejection email sent")


run_id = os.environ.get("RUN_ID", "")
sig = os.environ.get("SIG", "")

if not verify(run_id, sig):
    print("❌ Invalid signature.")
    sys.exit(1)

print(f"🗑 Rejected run {run_id}. Nothing uploaded to YouTube.")
send_confirm(run_id)
