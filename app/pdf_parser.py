import re
import unicodedata
import pymupdf  # PyMuPDF
from . import config

MIN_TEXT_CHARS = 20


class PdfError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def normalize(text: str) -> str:
    """Single normalizer used for storage, excerpt verification and evaluation."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"-\s*\n\s*", "", text)      # join words hyphenated across line breaks
    return re.sub(r"\s+", " ", text).strip()


def extract_pages(data: bytes) -> list[str]:
    """Return normalized text per page (index 0 = page 1) or raise PdfError with a clear message."""
    if b"%PDF-" not in data[:1024]:
        raise PdfError(415, "Not a PDF file (missing %PDF header).")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise PdfError(422, "Corrupt PDF: the file could not be opened.")
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise PdfError(422, "Encrypted/password-protected PDFs are not supported.")
        if doc.page_count == 0:
            raise PdfError(422, "Empty PDF: the file has no pages.")
        if doc.page_count > config.MAX_PAGES:
            raise PdfError(413, f"PDF has too many pages (limit {config.MAX_PAGES}).")
        try:
            pages = [normalize(p.get_text("text")) for p in doc]
            has_images = any(p.get_images() for p in doc)
        except Exception:
            raise PdfError(422, "Corrupt PDF: page content could not be read.")
    finally:
        doc.close()
    if sum(len(p) for p in pages) < MIN_TEXT_CHARS:
        if has_images:
            raise PdfError(422, "Unsupported: scanned/image-only PDF with no text layer (OCR is not supported).")
        raise PdfError(422, "Empty PDF: no extractable text found.")
    return pages
