"""
AI-gebaseerde e-mail classificatie met Claude.
"""
import logging
from dataclasses import dataclass
from anthropic import Anthropic, APIError
from utils.clean_body import clean_body
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    department: str
    confidence: float

    def __str__(self):
        return f"{self.department}|{self.confidence:.2f}"


class EmailClassifier:
    """Claude-powered e-mail categorisatie."""

    CATEGORIES = [
        "Customer Support",
        "Douane",
        "Import",
        "Transport",
        "Groupage",
    ]

    CONFIDENCE_THRESHOLD = 0.5

    # Snelle keyword-routing vóór Claude wordt aangeroepen.
    # Intentioneel alleen voor Customer Support en Groupage gedefinieerd —
    # de overige drie afdelingen worden altijd door Claude geclassificeerd.
    ROUTING_KEYWORDS: dict[str, list[str]] = {
        "Customer Support": [
            "offerte", "offertes", "preisanfrage", "quotation",
            "prijsaanvraag", "prijs aanvraag", "price quotation",
            "tarief", "tariefaanvraag",
            "luchtvracht", "lucht vracht", "air", "air-freight",
            "air freight", "airfreight",
            "breakbulk", "break-bulk", "break bulk",
        ],
        "Groupage": ["groupage", "lcl", "warehouse receipt", "warehousereceipt"],
    }

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-haiku-4-5-20251001"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, email_body: str, attachment_text: str = "") -> ClassificationResult:
        """
        Classificeer een e-mail naar afdeling met confidence score.

        Stap 1: snelle keyword-match (confidence 1.0)
        Stap 2: Claude classificatie met confidence
        Stap 3: keyword-gebaseerde fallback bij API-fout (confidence 0.0)

        Returns:
            ClassificationResult met department en confidence (0.0–1.0)
        """
        # Stap 1: snelle keyword-match — altijd zeker
        department = self._check_routing_keywords(email_body)
        if department:
            return ClassificationResult(department=department, confidence=1.0)

        # Stap 2: Claude
        try:
            prompt = self._build_prompt(email_body, attachment_text)
            message = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = message.content[0].text.strip()
            result = self._parse_response(raw)

            if result:
                logger.info(f"Claude classificatie: {result}")
                return result

            logger.warning(f"Onparseerbare Claude response: '{raw}' — fallback")
            return self._keyword_fallback(email_body, attachment_text)

        except APIError as e:
            logger.error(f"Claude API fout: {e}")
            return self._keyword_fallback(email_body, attachment_text)
        except Exception as e:
            logger.error(f"Classificatiefout: {e}", exc_info=True)
            return self._keyword_fallback(email_body, attachment_text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str) -> ClassificationResult | None:
        """
        Parseer Claude response in het formaat 'Department|0.85'.
        Geeft None terug als het formaat niet klopt of department onbekend is.
        """
        try:
            parts = raw.split("|")
            if len(parts) != 2:
                return None

            department = parts[0].strip()
            confidence = float(parts[1].strip())

            if department not in self.CATEGORIES:
                return None
            if not (0.0 <= confidence <= 1.0):
                return None

            return ClassificationResult(department=department, confidence=confidence)

        except (ValueError, IndexError):
            return None

    def _check_routing_keywords(self, text: str) -> str | None:
        """Snelle keyword-match vóór Claude wordt aangeroepen."""
        lowered = text.lower()
        for department, keywords in self.ROUTING_KEYWORDS.items():
            for keyword in keywords:
                if keyword in lowered:
                    logger.info(f"Keyword-match '{keyword}' → {department}")
                    return department
        return None

    def _build_prompt(self, email_body: str, attachment_text: str) -> str:
        """Bouw geoptimaliseerde classificatie-prompt."""
        categories_list = "\n".join(f"- {cat}" for cat in self.CATEGORIES)
        email_preview = clean_body(email_body)[:1500]
        attachment_preview = attachment_text[:1500] if attachment_text else "Geen bijlage"

        return f"""Je bent een e-mail routing assistent voor een logistiek bedrijf.

Classificeer deze e-mail naar EXACT één van deze afdelingen én geef een confidence score.

Afdelingen:
{categories_list}

Richtlijnen:
- Customer Support: Algemene vragen, klachten, service requests, offertes
- Douane: Invoerrechten, douane-documenten, clearance
- Import: Inkoop, leveranciers, import-orders
- Transport: Verzending, vervoer, tracking, FCL, boekingen
- Groupage: Groupage zendingen, LCL, samenvoeging, aanleveringen, commercial invoice

E-MAIL INHOUD:
{email_preview}

BIJLAGE TEKST:
{attachment_preview}

Antwoord met EXACT dit formaat (niets anders):
AfdelingsNaam|confidence

Waarbij confidence een getal is tussen 0.0 (volledig onzeker) en 1.0 (volledig zeker).
Voorbeeld: Transport|0.82"""

    def _keyword_fallback(self, email_body: str, attachment_text: str) -> ClassificationResult:
        """Simpele keyword-fallback bij Claude API-fouten. Confidence altijd 0.0."""
        text = (email_body + " " + attachment_text).lower()

        if any(kw in text for kw in ["douane", "customs", "clearance", "invoer"]):
            department = "Douane"
        elif any(kw in text for kw in ["transport", "verzending", "vervoer", "track"]):
            department = "Transport"
        elif any(kw in text for kw in ["import", "inkoop", "leverancier"]):
            department = "Import"
        elif any(kw in text for kw in ["groupage", "lcl", "consolidat"]):
            department = "Groupage"
        else:
            department = "Customer Support"

        return ClassificationResult(department=department, confidence=0.0)
