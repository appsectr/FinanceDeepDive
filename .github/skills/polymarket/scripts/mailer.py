"""
Email sender — sends HTML report via SendGrid REST API using only urllib.
Requires SENDGRID_API_KEY environment variable.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client


SENDGRID_URL = 'https://api.sendgrid.net/v3/mail/send'


def send_report(html_content, config, subject=None):
    """
    Send HTML report via SendGrid.
    Returns True on success, False on failure.
    """
    api_key = os.environ.get('SENDGRID_API_KEY', '')
    if not api_key:
        print("SENDGRID_API_KEY not set — skipping email")
        return False

    email_cfg = config.get('email', {})
    to_addr = email_cfg.get('to', '')
    from_addr = email_cfg.get('from', 'polymarket@financedeep.dive')
    from_name = email_cfg.get('from_name', 'Polymarket Analiz')

    if not to_addr:
        print("No recipient email configured — skipping")
        return False

    if subject is None:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        subject = f'[Polymarket] Gunluk Rapor — {date_str}'

    payload = {
        'personalizations': [
            {
                'to': [{'email': to_addr}],
                'subject': subject,
            }
        ],
        'from': {
            'email': from_addr,
            'name': from_name,
        },
        'content': [
            {
                'type': 'text/html',
                'value': html_content,
            }
        ],
    }

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    try:
        # SendGrid returns 202 on success with empty body
        resp = http_client.post_json(SENDGRID_URL, payload, headers=headers, timeout=30)
        print(f"Email sent to {to_addr}")
        return True
    except Exception as e:
        error_msg = str(e)
        # SendGrid 202 response has empty body, urllib may see this as "error"
        if '202' in error_msg:
            print(f"Email sent to {to_addr} (202 Accepted)")
            return True
        print(f"Email send failed: {error_msg}")
        return False
