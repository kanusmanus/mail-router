"""
Print recent emails from the mailbox for debugging.

Usage:
    uv run python scripts/print_emails.py
    uv run python scripts/print_emails.py --limit 20
    uv run python scripts/print_emails.py --folder sent
"""
import sys
import argparse
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from O365 import Account
from config import settings

NOISE_PATTERNS = [
    r'CAUTION:.*?content is safe\.?',
    r'WARNING:.*?content is safe\.?',
    r'This email originated from outside.*?content is safe\.?',
    r'EXTERNAL EMAIL.*?caution\.?',
    r'(?i)this message was sent from outside the company.*?\.',
    r'U ontvangt niet vaak e-mail van.*?belangrijk is\.?',
    r'You don\'t often get email from.*?why this is important\.?',
]

def strip_html(html: str) -> str:
    html = re.sub(r'<(style|script)[^>]*>.*?</(style|script)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    html = re.sub(r'\s+', ' ', html).strip()
    # Remove security/outlook banners
    for pattern in NOISE_PATTERNS:
        html = re.sub(pattern, '', html, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r'\s+', ' ', html).strip()

def print_emails(limit: int = 10, folder: str = "inbox"):
    account = Account(
        (settings.azure_client_id, settings.azure_client_secret),
        auth_flow_type='credentials',
        tenant_id=settings.azure_tenant_id,
        main_resource=settings.mailbox_email,
    )

    if not account.authenticate():
        print("❌ Authenticatie mislukt")
        sys.exit(1)

    mailbox = account.mailbox(resource=settings.mailbox_email)

    folder_map = {
        "inbox":   mailbox.inbox_folder,
        "sent":    mailbox.sent_folder,
        "drafts":  mailbox.drafts_folder,
        "deleted": mailbox.deleted_folder,
        "junk":    mailbox.junk_folder,
    }

    folder_key = folder.lower()
    if folder_key not in folder_map:
        print(f"❌ Onbekende folder '{folder}'")
        print(f"   Beschikbare opties: {', '.join(folder_map.keys())}")
        sys.exit(1)

    mail_folder = folder_map[folder_key]()
    messages = list(mail_folder.get_messages(limit=limit))

    if not messages:
        print(f"Geen berichten gevonden in {folder}")
        return

    print(f"\n{'='*60}")
    print(f"📬 {len(messages)} meest recente berichten in {folder} ({settings.mailbox_email})")
    print(f"{'='*60}\n")

    for i, msg in enumerate(messages, 1):
        attachment_names = []
        if msg.attachments:
            msg.attachments.download_attachments()
            attachment_names = [a.name for a in msg.attachments]

        body = strip_html(msg.body or "")

        print(f"[{i}] {'─'*50}")
        print(f"  Van:        {msg.sender}")
        print(f"  Onderwerp:  {msg.subject}")
        print(f"  Datum:      {msg.received}")
        print(f"  Gelezen:    {'Ja' if msg.is_read else 'Nee'}")
        print(f"  Bijlagen:   {', '.join(attachment_names) if attachment_names else 'Geen'}")
        print(f"  Body preview:")
        print(f"    {body[:300]}{'...' if len(body) > 300 else ''}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print recent emails from mailbox")
    parser.add_argument("--limit", type=int, default=10, help="Number of emails to fetch (default: 10)")
    parser.add_argument("--folder", type=str, default="inbox", help="Folder: inbox, sent, drafts, deleted, junk (default: inbox)")
    args = parser.parse_args()

    print_emails(limit=args.limit, folder=args.folder)
