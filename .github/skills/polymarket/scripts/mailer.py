"""
Email sender — sends HTML report via Gmail SMTP using only stdlib.
Requires GMAIL_KEY environment variable (App Password).
"""
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 465


def send_report(html_content, config, subject=None):
    """
    Send HTML report via Gmail SMTP.
    Returns True on success, False on failure.
    """
    app_password = os.environ.get('GMAIL_KEY', '')
    if not app_password:
        print("GMAIL_KEY not set — skipping email")
        return False

    email_cfg = config.get('email', {})
    to_addr = email_cfg.get('to', '')
    from_addr = email_cfg.get('from_email', '')
    from_name = email_cfg.get('from_name', 'Polymarket Analiz')

    if not to_addr or not from_addr:
        print("No sender/recipient email configured — skipping")
        return False

    if subject is None:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        subject = f'[Polymarket] Gunluk Rapor — {date_str}'

    msg = MIMEMultipart('alternative')
    msg['From'] = f'{from_name} <{from_addr}>'
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ctx) as server:
            server.login(from_addr, app_password)
            server.sendmail(from_addr, to_addr, msg.as_string())
        print(f"Email sent to {to_addr}")
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False
