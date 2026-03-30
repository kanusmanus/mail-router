"""
Vernieuw Microsoft Graph subscriptions (voor cron job).
Microsoft subscriptions verlopen na max 3 dagen.

Gebruik:
    uv run python scripts/renew_subscription.py

Cron (elke 2 dagen om 06:00):
    0 6 */2 * * cd /opt/mail-router && uv run python scripts/renew_subscription.py >> logs/renewal.log 2>&1
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

EXPIRY_DAYS = 2


def renew_subscriptions() -> bool:
    """Vernieuw alle actieve subscriptions die bij onze webhook horen."""
    try:
        account = get_authenticated_account()
    except RuntimeError as e:
        logger.error(f"❌ {e}")
        return False

    connection = account.con
    webhook_endpoint = f"{settings.webhook_url}/webhook"

    response = connection.get("https://graph.microsoft.com/v1.0/subscriptions")
    if not response or response.status_code != 200:
        logger.error(
            f"Kon subscriptions niet ophalen: "
            f"{response.status_code if response else 'geen response'}"
        )
        return False

    matching = [
        s for s in response.json().get("value", [])
        if webhook_endpoint in s.get("notificationUrl", "")
    ]

    if not matching:
        logger.warning(
            f"Geen subscriptions gevonden voor {webhook_endpoint}\n"
            "Voer setup_subscription.py uit om een nieuwe aan te maken."
        )
        return False

    new_expiry = (
        datetime.now(timezone.utc) + timedelta(days=EXPIRY_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

    renewed = failed = 0
    for sub in matching:
        sub_id = sub["id"]
        try:
            response = connection.patch(
                f"https://graph.microsoft.com/v1.0/subscriptions/{sub_id}",
                json={"expirationDateTime": new_expiry},
            )
            if response and response.status_code == 200:
                logger.info(f"✓ Subscription {sub_id} vernieuwd tot {new_expiry}")
                renewed += 1
            else:
                status = response.status_code if response else "geen response"
                body = response.text if response else ""
                logger.error(f"✗ Vernieuwen mislukt voor {sub_id} ({status}): {body}")
                failed += 1
        except Exception as e:
            logger.error(f"✗ Fout bij vernieuwen {sub_id}: {e}")
            failed += 1

    logger.info(f"Resultaat: {renewed} vernieuwd, {failed} mislukt")
    return failed == 0


if __name__ == "__main__":
    logger.info("=== Subscription Renewal ===")
    success = renew_subscriptions()
    sys.exit(0 if success else 1)
