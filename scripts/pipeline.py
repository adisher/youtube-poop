#!/usr/bin/env python3
"""
LLM Shorts — Pipeline
Generates video, stores it as a GitHub Actions artifact,
emails it to you as an attachment with Approve/Reject links.
No YouTube upload happens until you approve.
"""

import os, sys, json, random, smtplib, ssl, hmac, hashlib, base64
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime, timezone
from pathlib              import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import generate as gen


def sign(run_id: str) -> str:
    secret = os.environ.get("PIPELINE_SECRET", "change-me")
    return hmac.new(secret.encode(), run_id.encode(), hashlib.sha256).hexdigest()[:24]


def trigger_workflow(workflow_file: str, inputs: dict):
    """Trigger a GitHub Actions workflow_dispatch via API."""
    import urllib.request
    pat  = os.environ["GH_PAT"]
    repo = os.environ["GH_REPO"]
    url  = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
    body = json.dumps({"ref": "main", "inputs": inputs}).encode()
    req  = urllib.request.Request(url, data=body, headers={
        "Authorization": f"token {pat}",
        "Accept":        "application/vnd.github+json",
        "Content-Type":  "application/json",
    })
    req.get_method = lambda: "POST"
    with urllib.request.urlopen(req) as r:
        return r.status == 204


def send_email(kit: dict, run_id: str, sig: str, video_path: str):
    gmail  = os.environ["GMAIL_ADDRESS"]
    passwd = os.environ["GMAIL_APP_PASSWORD"]
    notify = os.environ.get("NOTIFY_EMAIL", gmail)
    title  = kit["title"]
    slot   = kit["slot"].capitalize()
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    repo   = os.environ["GH_REPO"]
    pat    = os.environ["GH_PAT"]

    # Approve/Reject = self-submitting HTML page that POSTs to GitHub API
    # We inline it as a data URI so clicking opens a tab, fires the action, shows result
    # Much simpler: just link directly — browser opens, page auto-fires fetch(), closes
    # We embed a tiny auto-fire page as base64 data URI for each button

    def make_action_page(workflow: str, label: str, color: str) -> str:
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:Arial,sans-serif;background:#111;color:#eee;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{background:#1a1a1a;border-radius:14px;padding:40px;text-align:center;max-width:380px}}
h2{{color:{color};margin:0 0 12px}}p{{color:#888;font-size:14px;margin:8px 0}}</style>
</head><body><div class="card">
<h2 id="t">Processing...</h2><p id="m">Please wait.</p>
</div><script>
(async()=>{{
  const r=await fetch('https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches',{{
    method:'POST',
    headers:{{'Authorization':'token {pat}','Accept':'application/vnd.github+json','Content-Type':'application/json'}},
    body:JSON.stringify({{ref:'main',inputs:{{run_id:'{run_id}',sig:'{sig}'}}}})
  }});
  if(r.status===204){{
    document.getElementById('t').textContent='{label} sent!';
    document.getElementById('t').style.color='{color}';
    document.getElementById('m').textContent='You can close this tab. Check your email for confirmation.';
  }}else{{
    document.getElementById('t').textContent='Error '+r.status;
    document.getElementById('m').textContent='Check your GH_PAT has actions:write scope.';
  }}
}})();
</script></body></html>"""
        b64 = base64.b64encode(html.encode()).decode()
        return f"data:text/html;base64,{b64}"

    approve_href = make_action_page("publish.yml", "✅ Approved", "#00b894")
    reject_href  = make_action_page("delete.yml",  "🗑 Rejected",  "#d63031")

    body_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#0d0d0d;color:#e0e0e0;padding:0}}
.w{{max-width:540px;margin:0 auto;padding:24px 16px}}
.hd{{background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:14px 14px 0 0;
     padding:24px;text-align:center}}
.hd h1{{margin:0;font-size:18px;color:#fff;font-weight:600}}
.hd small{{color:#555;font-size:12px;display:block;margin-top:5px}}
.bd{{background:#181818;padding:24px}}
.ttl{{font-size:17px;font-weight:700;color:#fff;margin-bottom:4px}}
.mt{{font-size:12px;color:#555;margin-bottom:20px}}
.tip{{background:#1a1f1a;border:1px solid #2a332a;border-radius:8px;
      padding:12px 16px;font-size:13px;color:#7dab7d;margin-bottom:20px;line-height:1.6}}
.actions{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.btn{{display:block;padding:15px 8px;border-radius:10px;text-decoration:none;
      text-align:center;font-size:15px;font-weight:700;color:#fff}}
.approve{{background:#00b894}}.reject{{background:#d63031}}
.ft{{background:#111;border-radius:0 0 14px 14px;padding:12px;
     text-align:center;font-size:11px;color:#444}}
</style></head><body>
<div class="w">
  <div class="hd">
    <h1>🎬 Short Ready for Review</h1>
    <small>{slot} slot &nbsp;·&nbsp; {now}</small>
  </div>
  <div class="bd">
    <div class="ttl">{title}</div>
    <div class="mt">Run ID: {run_id} &nbsp;·&nbsp; Topic: {kit['topic']}</div>
    <div class="tip">
      📎 Video is attached to this email — watch it directly in Gmail.<br>
      Then click Approve or Reject below.
    </div>
    <div class="actions">
      <a href="{approve_href}" class="btn approve">✅ Approve &amp; Upload</a>
      <a href="{reject_href}"  class="btn reject">🗑 Reject</a>
    </div>
  </div>
  <div class="ft">LLM Shorts &nbsp;·&nbsp; adilsher.pro</div>
</div>
</body></html>"""

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"[LLM Shorts] {title}"
    msg["From"]    = gmail
    msg["To"]      = notify
    msg.attach(MIMEText(body_html, "html"))

    # Attach the video
    with open(video_path, "rb") as f:
        att = MIMEBase("video", "mp4")
        att.set_payload(f.read())
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", "attachment",
                   filename=f"{kit['topic']}.mp4")
    msg.attach(att)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(gmail, passwd)
        s.sendmail(gmail, notify, msg.as_string())
    print(f"  ✓ Email sent → {notify}")


def run(slot: str, topic_id: str | None = None):
    topic_id = topic_id or random.choice(list(gen.TOPICS.keys()))
    run_id   = os.environ.get("GITHUB_RUN_ID", f"local-{int(datetime.now().timestamp())}")
    out_dir  = f"/tmp/llm-shorts-{slot}-{topic_id}"

    print(f"\n{'='*52}\n  LLM Shorts — {slot.upper()} — {topic_id}\n{'='*52}\n")

    # 1. Generate video
    kit = gen.generate(topic_id, slot, out_dir)

    # 2. Save kit.json with run_id (artifact upload handled by workflow YAML)
    kit["run_id"] = run_id
    kit_path = os.path.join(out_dir, "kit.json")
    with open(kit_path, "w") as f:
        json.dump(kit, f, indent=2)

    # 3. Send email with video attached + approve/reject links
    print("\n📧 Sending email...")
    sig = sign(run_id)
    send_email(kit, run_id, sig, kit["video"])

    print(f"\n✅ Done. Check your inbox.")
    # Print kit path so workflow can find it for artifact upload
    print(f"KIT_DIR={out_dir}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot",  default="morning", choices=["morning", "evening"])
    ap.add_argument("--topic", default=None)
    args = ap.parse_args()
    run(args.slot, args.topic)
