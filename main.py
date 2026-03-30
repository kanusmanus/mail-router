"""
FastAPI webhook server voor Microsoft Graph notifications.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings
from services.email_processor import EmailProcessor
from services.queue import email_queue
from services.tasks import process_email_task
from services.subscription_manager import SubscriptionManager

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# App-brede singletons — aangemaakt bij startup, niet bij import
# ------------------------------------------------------------------
email_processor: EmailProcessor | None = None
subscription_manager: SubscriptionManager | None = None

# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------

async def _renewal_loop():
    """Vernieuw de Graph webhook subscription elke 46 uur."""
    while True:
        await asyncio.sleep(46 * 3600)
        logger.info("Vernieuwen webhook subscription...")
        subscription_manager.renew()


async def _process_unread_emails_async():
    """Verwerk ongelezen e-mails in de achtergrond (blokkeert startup niet)."""
    try:
        mailbox = email_processor.account.mailbox(resource=settings.mailbox_email)
        inbox = mailbox.inbox_folder()
        unread = list(
            inbox.get_messages(limit=10, query="isRead eq false", order_by="receivedDateTime")
        )
        if not unread:
            logger.info("Geen ongelezen e-mails gevonden bij startup")
            return
        logger.info(f"📬 {len(unread)} ongelezen e-mail(s) in backlog — verwerken...")
        for msg in unread:
            email_queue.enqueue(process_email_task, msg.object_id)
        logger.info("Backlog in wachtrij geplaatst")
    except Exception as e:
        logger.error(f"Fout bij verwerken backlog: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global email_processor, subscription_manager

    # Initialiseer services (fouten hier stoppen de startup intentioneel)
    try:
        email_processor = EmailProcessor()
        subscription_manager = SubscriptionManager(email_processor.account)
    except RuntimeError as e:
        logger.critical(f"❌ Startup mislukt: {e}")
        raise

    # Laad bestaande subscription of maak nieuwe aan
    subscription_manager.initialize()

    # Verwerk backlog asynchroon (blokkeert startup niet)
    asyncio.create_task(_process_unread_emails_async())

    # Periodieke renewal
    renewal_task = asyncio.create_task(_renewal_loop())

    logger.info("🚀 Mail Router gestart")
    yield

    renewal_task.cancel()
    logger.info("👋 Mail Router gestopt")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="Mail Router",
    description="Automatische e-mail routing met AI classificatie",
    version="1.0.0",
    lifespan=lifespan,
    # Schakel automatische docs uit in productie
    docs_url="/docs" if True else None,
    redoc_url=None,
)

# ------------------------------------------------------------------
# Security helper voor /test endpoint
# ------------------------------------------------------------------

_bearer = HTTPBearer()


def _require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Simpele Bearer token check voor interne endpoints."""
    if credentials.credentials != settings.webhook_client_state:
        raise HTTPException(status_code=401, detail="Ongeldig token")


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "Mail Router",
        "environment": settings.environment,
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "authenticated": email_processor.account.is_authenticated if email_processor else False,
        "mailbox": settings.mailbox_email,
        "subscription_id": subscription_manager._subscription_id if subscription_manager else None,
    }


@app.post("/webhook")
async def handle_webhook(request: Request):
    """
    Microsoft Graph webhook endpoint.
    Ontvangt notificaties bij nieuwe e-mails in de inbox.
    Reageert altijd met 202 (Microsoft vereiste).
    """
    try:
        # Eenmalige Microsoft validatiehandshake
        validation_token = request.query_params.get("validationToken")
        if validation_token:
            logger.info("Webhook validatie ontvangen")
            return Response(content=validation_token, media_type="text/plain")

        data = await request.json()
        notifications = data.get("value", [])

        if not notifications:
            return Response(status_code=202)

        logger.info(f"📧 {len(notifications)} notification(s) ontvangen")
        processed = failed = 0

        for notification in notifications:
            try:
                # Valideer clientState — gooi nep-notificaties weg
                if notification.get("clientState") != settings.webhook_client_state:
                    logger.warning("Ongeldige clientState — notification genegeerd")
                    continue

                message_id = notification.get("resourceData", {}).get("id")
                if not message_id:
                    logger.warning(f"Notification zonder message_id: {notification}")
                    failed += 1
                    continue

                if email_queue.enqueue(process_email_task, message_id):
                    processed += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Fout bij verwerken notification: {e}")
                failed += 1

        logger.info(f"✓ In wachtrij: {processed} | ✗ Mislukt: {failed}")
        return Response(status_code=202)

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return Response(status_code=202)   # altijd 202 terug naar Microsoft


@app.post("/test", dependencies=[Depends(_require_api_key)])
async def test_classification(request: Request):
    """
    Handmatig testen van de classificatie.
    Vereist: Authorization: Bearer <webhook_client_state>
    """
    try:
        data = await request.json()
        department = email_processor.classifier.classify(
            email_body=data.get("email_body", ""),
            attachment_text=data.get("attachment_text", ""),
        )
        target_email = settings.department_emails.get(
            department, settings.fallback_email
        )
        return {"department": department, "target_email": target_email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=(settings.environment == "development"),
    )
