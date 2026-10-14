import re
import unicodedata
import pymupdf  # PyMuPDF
from . import config

MIN_TEXT_CHARS = 20
_ocr_engine = None  # created once on first use (takes about 1.5 s)


class PdfError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def normalize(text: str) -> str:
    """Single normalizer used for storage, excerpt verification and evaluation."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"-\s*\n\s*", "", text)      # join words hyphenated across line breaks
    return re.sub(r"\s+", " ", text).strip()


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            raise PdfError(422, "OCR is enabled but not installed. Run: pip install -r requirements-ocr.txt")
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_page(page) -> str:
    """Render one page to an image, run OCR, return normalized text (lines in top-to-bottom order)."""
    png = page.get_pixmap(dpi=config.OCR_DPI).tobytes("png")
    result, _ = _get_ocr()(png)          # list of [box, text, confidence] or None
    if not result:
        return ""
    lines = sorted(result, key=lambda r: (r[0][0][1], r[0][0][0]))
    return normalize(" ".join(r[1] for r in lines))


def extract_pages_ex(data: bytes) -> tuple[list[str], bool]:
    """Return (normalized text per page, ocr_used). Index 0 = page 1. Raises PdfError with a clear message."""
    if b"%PDF-" not in data[:1024]:
        raise PdfError(415, "Not a PDF file (missing %PDF header).")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise PdfError(422, "Corrupt PDF: the file could not be opened.")
    ocr_used = False
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
        # OCR only for image-only PDFs, and only when switched on
        if sum(len(p) for p in pages) < MIN_TEXT_CHARS and has_images and config.OCR_ENABLED:
            if doc.page_count > config.OCR_MAX_PAGES:
                raise PdfError(422, f"Scanned PDF has {doc.page_count} pages; the OCR limit is {config.OCR_MAX_PAGES} pages.")
            try:
                pages = [_ocr_page(p) for p in doc]
            except PdfError:
                raise
            except Exception:
                raise PdfError(422, "OCR failed on this PDF.")
            ocr_used = True
    finally:
        doc.close()
    if sum(len(p) for p in pages) < MIN_TEXT_CHARS:
        if ocr_used:
            raise PdfError(422, "Unsupported: scanned PDF, but OCR found no readable text.")
        if has_images:
            raise PdfError(422, "Unsupported: scanned/image-only PDF with no text layer (OCR is not supported).")
        raise PdfError(422, "Empty PDF: no extractable text found.")
    return pages, ocr_used


def extract_pages(data: bytes) -> list[str]:
    """Backwards-compatible wrapper: just the pages."""
    return extract_pages_ex(data)[0]