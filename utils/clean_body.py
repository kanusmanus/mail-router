import re

NOISE_PATTERNS = [
    r'CAUTION:.*?content is safe\.?',
    r'WARNING:.*?content is safe\.?',
    r'This email originated from outside.*?content is safe\.?',
    r'EXTERNAL EMAIL.*?caution\.?',
    r'(?i)this message was sent from outside the company.*?\.',
    # Microsoft Outlook "unknown sender" banner (NL + EN)
    r'U ontvangt niet vaak e-mail van.*?belangrijk is\.?',
    r'You don\'t often get email from.*?why this is important\.?',
]

def _strip_html(html: str) -> str:
    html = re.sub(r'<(style|script)[^>]*>.*?</(style|script)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)        
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', html).strip()

def clean_body(text: str) -> str:
    text = _strip_html(text)
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r'\s+', ' ', text).strip()

