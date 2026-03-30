"""
Eenmalige setup van Microsoft Graph subscription.
Run dit script NADAT de server draait en bereikbaar is via HTTPS.

Gebruik:
    uv run python scripts/setup_subscription.py
"""
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from utils.auth import get_authenticated_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

EXPIRY_DAYS = 2  # Microsoft staat max 3 dagen toe; 2 is veiliger


def list_existing_subscriptions(connection, webhook_endpoint: str) -> list:
    response = connection.get("https://graph.microsoft.com/v1.0/subscriptions")
    if not response or response.status_code != 200:
        logger.warning(
            f"Kon subscriptions niet ophalen: "
            f"{response.status_code if response else 'geen response'}"
        )
        return []
    return [
        s for s in response.json().get("value", [])
        if webhook_endpoint in s.get("notificationUrl", "")
    ]


def delete_subscription(connection, sub_id: str) -> bool:
    response = connection.delete(
        f"https://graph.microsoft.com/v1.0/subscriptions/{sub_id}"
    )
    return response and response.status_code == 204


def create_subscription(connection, webhook_endpoint: str) -> dict | None:
    expiry = (
        datetime.now(timezone.utc) + timedelta(days=EXPIRY_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

    payload = {
        "changeType": "created",
        "notificationUrl": webhook_endpoint,
        "resource": f"/users/{settings.mailbox_email}/mailFolders/Inbox/messages",
        "expirationDateTime": expiry,
        "clientState": settings.webhook_client_state,
    }

    response = connection.post(
        "https://graph.microsoft.com/v1.0/subscriptions", json=payload
    )

    if response and response.status_code == 201:
        return response.json()

    status = response.status_code if response else "geen response"
    body = response.text if response else ""
    logger.error(f"Aanmaken mislukt ({status}): {body}")
    return None


def setup_subscription():
    webhook_endpoint = f"{settings.webhook_url}/webhook"

    logger.info("=== Microsoft Graph Subscription Setup ===")
    logger.info(f"Mailbox:  {settings.mailbox_email}")
    logger.info(f"Webhook:  {webhook_endpoint}")

    account = get_authenticated_account()
    connection = account.con

    existing = list_existing_subscriptions(connection, webhook_endpoint)

    if existing:
        logger.info(f"Gevonden {len(existing)} bestaande subscription(s):")
        for sub in existing:
            logger.info(f"  - ID: {sub['id']}  Verloopt: {sub['expirationDateTime']}")

        antwoord = input("\nVerwijderen en opnieuw aanmaken? (y/n): ").strip().lower()
        if antwoord != "y":
            logger.info("Bestaande subscription behouden.")
            return True

        for sub in existing:
            if delete_subscription(connection, sub["id"]):
                logger.info(f"✓ Subscription {sub['id']} verwijderd")
            else:
                logger.warning(f"Kon subscription {sub['id']} niet verwijderen")

    logger.info("Subscription aanmaken...")
    result = create_subscription(connection, webhook_endpoint)

    if result:
        logger.info("✅ Subscription succesvol aangemaakt!")
        logger.info(f"   ID:        {result['id']}")
        logger.info(f"   Resource:  {result['resource']}")
        logger.info(f"   Verloopt:  {result['expirationDateTime']}")
        return True

    logger.error("❌ Setup mislukt")
    return False


if __name__ == "__main__":
    try:
        success = setup_subscription()
        sys.exit(0 if success else 1)
    except RuntimeError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Afgebroken")
        sys.exit(1)
