import fitz  # PyMuPDF
import io
import logging
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)


class PDFExtractor:

    def is_pdf(self, filename: str) -> bool:
        return filename.lower().endswith(".pdf")

    def extract_text_from_bytes(self, pdf_bytes: bytes, max_pages: int = 3) -> str:
        """
        Snelle PDF text extractie.
        - gebruikt PyMuPDF (zeer snel)
        - OCR fallback als geen tekst gevonden
        """

        try:
            import base64

            if isinstance(pdf_bytes, str):
                try:
                    pdf_bytes = base64.b64decode(pdf_bytes)
                except Exception:
                    pdf_bytes = pdf_bytes.encode("utf-8")

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            texts = []

            # Beperk aantal pagina's voor performance
            for page in doc[:max_pages]:
                text = page.get_text().strip()
                if text:
                    texts.append(text)

            combined = "\n".join(texts)

            # Als er tekst is gevonden -> klaar
            if combined:
                return combined

            # Anders OCR fallback
            logger.info("Geen tekst gevonden in PDF — OCR fallback")

            ocr_texts = []

            for page in doc[:max_pages]:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img)

                if text:
                    ocr_texts.append(text)

            return "\n".join(ocr_texts)

        except Exception as e:
            logger.error(f"PDF extractie fout: {e}", exc_info=True)
            return ""
