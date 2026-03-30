# Mail Router

Automatisch e-mail routing systeem voor logistieke bedrijven. Inkomende e-mails worden via Microsoft Graph onderschept, geclassificeerd door Claude AI, en doorgestuurd naar de juiste afdeling.

## Hoe het werkt

```
Klant → transport@domein.com
           ↓ (Exchange redirect rule, ingesteld door admin)
        ai-ifc-in@domein.com  ←  Microsoft Graph webhook
           ↓
        Claude AI classificeert + confidence score
           ↓
   confidence ≥ 0.5          confidence < 0.5
        ↓                          ↓
  geclassificeerd dept      origineel adres (transport@domein.com)
```

## Stack

- **FastAPI** — webhook server voor Microsoft Graph notificaties
- **O365** — Microsoft Graph authenticatie en mailbox toegang
- **Anthropic Claude** (Haiku) — e-mail classificatie met confidence score
- **RQ + Valkey/Redis** — asynchrone taakwachtrij
- **nginx** — reverse proxy met TLS
- **systemd** — procesbeheer

## Vereisten

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Valkey of Redis (`sudo pacman -S redis` / `sudo apt install redis-server`)
- Een Microsoft 365 tenant met een service account
- Een Anthropic API key
- Een publiek bereikbaar HTTPS endpoint (voor de webhook)

## Installatie

```bash
git clone https://github.com/jouworg/mail-router.git
cd mail-router
uv sync
cp .env.example .env
# Vul .env in (zie hieronder)
```

## Configuratie (.env)

```ini
# Azure AD
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=jouw-client-secret
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Applicatie
WEBHOOK_URL=https://mail-router.jouwdomein.nl
MAILBOX_EMAIL=ai-ifc-in@domein.com        # de beheerde mailbox
SERVICE_ACCOUNT_EMAIL=svc@domein.com
SERVICE_ACCOUNT_PASSWORD=wachtwoord

# Webhook beveiliging
# Genereer met: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
WEBHOOK_CLIENT_STATE=vervang-dit-met-random-string

ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Lokaal draaien

Start Valkey/Redis:
```bash
sudo systemctl start valkey   # Arch
sudo systemctl start redis    # Ubuntu/Debian
```

Start de webhook server en worker elk in een aparte terminal:
```bash
# Terminal 1
uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2
uv run rq worker emails
```

## Webhook subscription aanmaken

De server moet via HTTPS bwaar zijn voordat je dit uitvoert — Microsoft valideert de URL direct.

```bash
uv run python scripts/setup_subscription.py
```

Subscriptions verlopen na maximaal 3 dagen. De server vernieuwt automatisch elke 46 uur. Als extra zekerheid:

```bash
# Handmatig vernieuwen
uv run python scripts/renew_subscription.py

# Of als cron (elke 2 dagen om 06:00)
0 6 */2 * * cd /opt/mail-router && uv run python scripts/renew_subscription.py >> logs/renewal.log 2>&1
```

## Classificatie

E-mails worden gerouteerd naar één van vijf afdelingen:

| Afdeling | Voorbeelden |
|---|---|
| Customer Support | Offertes, algemene vragen, klachten, luchtvracht |
| Douane | Invoerrechten, clearance, douane-documenten |
| Import | Inkoop, leveranciers, import-orders |
| Transport | FCL, boekingen, tracking, verzendingen |
| Groupage | LCL, samenvoeging, warehouse receipts |

Classificatie verloopt in drie stappen:
1. **Keyword-match** — snelle deterministische routing voor bekende termen (confidence 1.0)
2. **Claude AI** — classificatie + confidence score in formaat `Transport|0.82`
3. **Keyword-fallback** — bij Claude API-fouten (confidence 0.0 → altijd naar origineel adres)

## Productie deployment

Zie [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md) voor de volledige stap-voor-stap handleiding met systemd, nginx en TLS.

Kort overzicht:
```bash
# systemd services installeren
sudo cp deploy/mail-router.service        /etc/systemd/system/
sudo cp deploy/mail-router-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mail-router mail-router-worker

# nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/mail-router
sudo ln -s /etc/nginx/sites-available/mail-router /etc/nginx/sites-enabled/
sudo certbot --nginx -d mail-router.jouwdomein.nl
```

## Testen

Het `/test` endpoint is alleen bereikbaar via localhost. Gebruik een SSH tunnel:

```bash
# Op je lokale machine
ssh -L 8000:127.0.0.1:8000 user@jouw-vps

# Dan lokaal
curl -X POST http://localhost:8000/test \
  -H "Authorization: Bearer <webhook_client_state>" \
  -H "Content-Type: application/json" \
  -d '{"email_body": "Ik heb een vraag over mijn FCL zending"}'
```

## Projectstructuur

```
mail-router/
├── main.py                        # FastAPI app + webhook endpoint
├── config.py                      # Instellingen via pydantic-settings
├── services/
│   ├── ai_classifier.py           # Claude classificatie + confidence
│   ├── email_processor.py         # E-mail ophalen, classificeren, routeren
│   ├── subscription_manager.py    # Graph webhook subscription beheer
│   ├── queue.py                   # RQ wachtrij initialisatie
│   └── tasks.py                   # RQ taakdefinities
├── utils/
│   ├── auth.py                    # Gedeelde O365 authenticatie factory
│   ├── clean_body.py              # HTML strippen + ruis verwijderen
│   └── pdf_extractor.py           # PyMuPDF + OCR fallback
├── scripts/
│   ├── setup_subscription.py      # Eenmalige webhook setup
│   └── renew_subscription.py      # Subscription vernieuwen (cron)
└── deploy/
    ├── DEPLOYMENT.md              # Volledige deployment handleiding
    ├── mail-router.service        # systemd unit (server)
    ├── mail-router-worker.service # systemd unit (worker)
    └── nginx.conf                 # nginx reverse proxy config
```

## Azure AD vereisten

- App registration met **public client flows** ingeschakeld
- `Mail.ReadWrite` en `Mail.Send` **delegated** permissies
- Service account met toegang tot de beheerde mailbox
- Eventueel: `ApplicationAccessPolicy` in Exchange Online om toegang te beperken tot alleen de beheerde mailbox
