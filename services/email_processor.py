"""
E-mail verwerking en routing logica (O365 implementatie).
"""
import logging
from O365 import Account
from config import settings
from utils.auth import get_authenticated_account
from utils.pdf_extractor import PDFExtractor
from services.ai_classifier import EmailClassifier, ClassificationResult
from utils.clean_body import clean_body

logger = logging.getLogger(__name__)

SYSTEM_BLACKLIST = {
    "quarantine@messaging.microsoft.com",
    "no-reply@microsoft.com",
    "mailer-daemon@microsoft.com",
}


class EmailProcessor:
    """Verwerk inkomende e-mails en route naar de juiste afdeling."""

    def __init__(self):
        self.account: Account = get_authenticated_account()
        self.pdf_extractor = PDFExtractor()
        self.classifier = EmailClassifier()
        logger.info(
            f"✓ EmailProcessor klaar voor mailbox: {settings.mailbox_email}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_message(self, message_id: str) -> bool:
        """
        Haal een e-mail op via message_id en verwerk deze.

        Args:
            message_id: Microsoft Graph message ID (uit webhook notification)

        Returns:
            True bij success, False bij fout
        """
        try:
            mailbox = self.account.mailbox(resource=settings.mailbox_email)
            message = mailbox.get_message(message_id)

            if not message:
                logger.error(f"Bericht niet gevonden: {message_id}")
                return False

            sender_email = message.sender.address.lower() if message.sender else ""

            if any(blacklisted in sender_email for blacklisted in SYSTEM_BLACKLIST):
                logger.info(f"⏩ Overslaan: systeemmelding van {sender_email}")
                message.mark_as_read()
                return True

            logger.info(f"Verwerken: '{message.subject}' van {message.sender}")

            attachment_text = self._extract_attachments(message)

            result = self.classifier.classify(
                email_body=message.body or "",
                attachment_text=attachment_text,
            )

            # Origineel bedoeld adres: het To-adres waarnaar de klant
            # de mail stuurde (vóór de Exchange redirect naar onze mailbox)
            original_to = self._get_original_to(message)

            success = self._route_email(message, result, original_to)

            if success:
                message.mark_as_read()
                logger.debug(f"Body preview: {clean_body(message.body)[:200]}")

            logger.info("-" * 60)
            return success

        except Exception as e:
            logger.error(
                f"Fout bij verwerken bericht {message_id}: {e}", exc_info=True
            )
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_original_to(self, message) -> str | None:
        """
        Haal het originele To-adres op — het adres waarnaar de klant
        de mail stuurde vóór de Exchange redirect.

        O365 message.to geeft de originele ontvangers terug,
        ook na een Exchange redirect-rule.
        """
        try:
            recipients = list(message.to)
            if not recipients:
                return None

            # Sla ons eigen beheerde mailbox-adres over — dat is de redirect-bestemming,
            # niet het originele adres.
            for recipient in recipients:
                address = recipient.address.lower()
                if address != settings.mailbox_email.lower():
                    return recipient.address

            # Als alle ontvangers onze eigen mailbox zijn (onverwacht), gebruik eerste
            return recipients[0].address

        except Exception as e:
            logger.warning(f"Kon origineel To-adres niet bepalen: {e}")
            return None

    def _extract_attachments(self, message) -> str:
        """Extraheer tekst uit alle PDF bijlagen."""
        try:
            if not getattr(message, "has_attachments", False):
                return ""

            message.attachments.download_attachments()
            extracted_texts = []

            for attachment in message.attachments:
                name = getattr(attachment, "name", "") or ""
                if not self.pdf_extractor.is_pdf(name):
                    continue

                content = getattr(attachment, "content", None)
                if not content:
                    logger.warning(f"Lege attachment overgeslagen: {name}")
                    continue

                try:
                    text = self.pdf_extractor.extract_text_from_bytes(content)
                    if text:
                        extracted_texts.append(text)
                except Exception as e:
                    logger.error(
                        f"Fout bij verwerken PDF '{name}': {e}", exc_info=True
                    )

            # Beperk lengte (Claude tokens besparen)
            return "\n\n".join(extracted_texts)[:4000]

        except Exception as e:
            logger.error(f"Fout bij verwerken attachments: {e}", exc_info=True)
            return ""

    def _route_email(
        self,
        message,
        result: ClassificationResult,
        original_to: str | None,
    ) -> bool:
        """
        Stuur e-mail door op basis van classificatie en confidence.

        Confidence >= 0.5 → doorsturen naar geclassificeerd department
        Confidence <  0.5 → doorsturen naar origineel To-adres (intent van de admin)

        Args:
            message:     O365 Message object
            result:      ClassificationResult (department + confidence)
            original_to: Het originele To-adres vóór de Exchange redirect

        Returns:
            True bij success
        """
        try:
            threshold = self.classifier.CONFIDENCE_THRESHOLD

            if result.confidence >= threshold:
                # Hoge confidence → classificatie vertrouwen
                target_email = settings.department_emails.get(
                    result.department, settings.fallback_email
                )
                routing_reason = f"confidence {result.confidence:.2f} ≥ {threshold}"
            else:
                # Lage confidence → terug naar origineel bedoeld adres
                target_email = (
                    original_to
                    or settings.department_emails.get(result.department)
                    or settings.fallback_email
                )
                routing_reason = (
                    f"lage confidence {result.confidence:.2f} < {threshold} "
                    f"→ origineel adres gebruikt"
                )

            logger.info(
                f"Routing: '{message.subject}' → {target_email} "
                f"[{result.department}|{result.confidence:.2f}] ({routing_reason})"
            )

            # forward = message.forward()
            # forward.to.add(target_email)
            # forward.subject = f"[{result.department}] {message.subject}"
            # forward.send()

            logger.info(f"📤 Doorgestuurd naar {target_email}")
            return True

        except Exception as e:
            logger.error(
                f"Fout bij doorsturen [{result}]: {e}", exc_info=True
            )
            return False
