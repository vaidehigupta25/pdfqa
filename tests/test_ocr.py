from pathlib import Path

import pytest

from app import config
from app.pdf_parser import PdfError, extract_pages_ex

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
OCR_PDF = SAMPLES / "ocr" / "scanned_ocr.pdf"
A = {"X-API-Key": "test-alice-key"}


def test_ocr_off_still_rejects_scanned(monkeypatch):
    monkeypatch.setattr(config, "OCR_ENABLED", False)
    with pytest.raises(PdfError) as e:
        extract_pages_ex(OCR_PDF.read_bytes())
    assert e.value.status == 422


def test_ocr_on_reads_the_scanned_page(monkeypatch):
    pytest.importorskip("rapidocr_onnxruntime")
    monkeypatch.setattr(config, "OCR_ENABLED", True)
    pages, used = extract_pages_ex(OCR_PDF.read_bytes())
    text = " ".join(pages).lower()
    assert used is True
    assert "parking" in text and "hours" in text


def test_upload_with_ocr_sets_flag(client, monkeypatch):
    pytest.importorskip("rapidocr_onnxruntime")
    monkeypatch.setattr(config, "OCR_ENABLED", True)
    r = client.post("/documents", headers=A,
                    files={"file": ("scanned_ocr.pdf", OCR_PDF.read_bytes(), "application/pdf")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    doc = next(d for d in client.get("/documents", headers=A).json() if d["id"] == doc_id)
    assert doc["ocr_used"] is True
    client.delete(f"/documents/{doc_id}", headers=A)      # keep the shared test database clean