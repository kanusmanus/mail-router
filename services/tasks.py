"""
RQ taakdefinities.
Importeert de gedeelde processor-instantie zodat er geen dubbele
authenticatiesessies ontstaan.
"""
from __future__ import annotations
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Lazy import — wordt pas geïnitialiseerd door de RQ worker, niet door de
# FastAPI server. Zo vermijden we dat de worker een tweede Account aanmaakt
# als de server zelf al één heeft.
_processor = None


def _get_processor():
    global _processor
    if _processor is None:
        from services.email_processor import EmailProcessor
        _processor = EmailProcessor()
    return _processor


def process_email_task(message_id: str) -> bool:
    """
    Verwerk één e-mail. Wordt uitgevoerd door de RQ worker.
    Geeft True terug bij succes, False bij fout.
    """
    try:
        return _get_processor().process_message(message_id)
    except Exception as e:
        logger.error(f"Taak mislukt voor message_id {message_id}: {e}", exc_info=True)
        return False

