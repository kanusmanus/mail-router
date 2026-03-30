"""
Microsoft Graph webhook subscription beheer.
Registreert en vernieuwt de mailbox webhook automatisch.
"""
import logging
from datetime import datetime, timezone, timedelta
from O365 import Account
from config import settings

logger = logging.getLogger(__name__)

# Graph webhook subscriptions verlopen na maximaal 4230 minuten (~3 dagen)
SUBSCRIPTION_EXPIRY_HOURS = 47


class SubscriptionManager:
    def __init__(self, account: Account):
        self.account = account
        self._subscription_id: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """
        Probeer een bestaande subscription te laden.
        Maakt een nieuwe aan als er geen gevonden wordt.
        Aanroepen tijdens app startup.
        """
        existing = self._find_existing_subscription()
        if existing:
            self._subscription_id = existing["id"]
            logger.info(
                f"✓ Bestaande subscription geladen: {self._subscription_id} "
                f"(verloopt {existing.get('expirationDateTime')})"
            )
            return True

        logger.info("Geen bestaande subscription gevonden — nieuwe aanmaken")
        return self.register()

    def register(self) -> bool:
        """Registreer een nieuwe webhook subscription bij Microsoft Graph."""
        try:
            connection = self.account.con
            expiry = _expiry_timestamp(SUBSCRIPTION_EXPIRY_HOURS)

            payload = {
                "changeType": "created",
                "notificationUrl": f"{settings.webhook_url}/webhook",
                "resource": f"/users/{settings.mailbox_email}/mailFolders/Inbox/messages",
                "expirationDateTime": expiry,
                "clientState": settings.webhook_client_state,
            }

            response = connection.post(
                "https://graph.microsoft.com/v1.0/subscriptions", json=payload
            )

            if response and response.status_code == 201:
                data = response.json()
                self._subscription_id = data.get("id")
                logger.info(
                    f"✓ Webhook subscription aangemaakt: {self._subscription_id} "
                    f"(verloopt {data.get('expirationDateTime')})"
                )
                return True

            status = response.status_code if response else "geen response"
            body = response.text if response else ""
            logger.error(f"Subscription aanmaken mislukt ({status}): {body}")
            return False

        except Exception as e:
            logger.error(f"Fout bij aanmaken subscription: {e}", exc_info=True)
            return False

    def renew(self) -> bool:
        """Vernieuw de bestaande subscription. Maakt een nieuwe aan als ID ontbreekt."""
        if not self._subscription_id:
            logger.warning("Geen subscription ID bekend — opnieuw registreren")
            return self.initialize()

        try:
            connection = self.account.con
            expiry = _expiry_timestamp(SUBSCRIPTION_EXPIRY_HOURS)
            url = f"https://graph.microsoft.com/v1.0/subscriptions/{self._subscription_id}"

            response = connection.patch(url, json={"expirationDateTime": expiry})

            if response and response.status_code == 200:
                logger.info(
                    f"✓ Subscription {self._subscription_id} vernieuwd tot {expiry}"
                )
                return True

            logger.warning(
                f"Vernieuwen mislukt ({response.status_code if response else 'geen response'}) "
                "— nieuw aanmaken"
            )
            self._subscription_id = None
            return self.register()

        except Exception as e:
            logger.error(f"Fout bij vernieuwen subscription: {e}", exc_info=True)
            return False

    def delete(self) -> None:
        """Verwijder subscription (optioneel bij graceful shutdown)."""
        if not self._subscription_id:
            return
        try:
            self.account.con.delete(
                f"https://graph.microsoft.com/v1.0/subscriptions/{self._subscription_id}"
            )
            logger.info(f"Subscription {self._subscription_id} verwijderd")
        except Exception as e:
            logger.warning(f"Fout bij verwijderen subscription: {e}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_existing_subscription(self) -> dict | None:
        """
        Zoek een actieve subscription voor onze webhook URL.
        Geeft de eerste match terug, of None.
        """
        try:
            response = self.account.con.get(
                "https://graph.microsoft.com/v1.0/subscriptions"
            )
            if not response or response.status_code != 200:
                logger.warning(
                    f"Subscriptions ophalen mislukt: "
                    f"{response.status_code if response else 'geen response'}"
                )
                return None

            webhook_endpoint = f"{settings.webhook_url}/webhook"
            for sub in response.json().get("value", []):
                if webhook_endpoint in sub.get("notificationUrl", ""):
                    return sub

        except Exception as e:
            logger.warning(f"Fout bij ophalen subscriptions: {e}")

        return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _expiry_timestamp(hours: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
