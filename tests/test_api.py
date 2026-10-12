import pymupdf
import pytest
from app.pdf_parser import normalize
from tests.conftest import A, B, SAMPLES, upload


def page_text(path, page):  # independent check against the ORIGINAL file, page numbers start at 1
    return normalize(pymupdf.open(path)[page - 1].get_text())


def test_requires_valid_key(client):
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.post("/ask", json={"question": "hi"}).status_code == 401


def test_three_pdfs_processed_with_status(client, docs):
    r = client.get("/documents", headers=A).json()
    assert len([d for d in r if d["status"] == "ready"]) >= 3
    assert all(d["page_count"] > 0 for d in r if d["status"] == "ready")


@pytest.mark.parametrize("name,status,fragment", [
    ("corrupt.pdf", 422, "Corrupt"), ("truncated.pdf", 422, "Corrupt"),
    ("empty.pdf", 422, "Empty"), ("scanned.pdf", 422, "scanned"), ("not_a_pdf.pdf", 415, "Not a PDF")])
def test_invalid_uploads_have_clear_errors(client, name, status, fragment):
    r = upload(client, A, SAMPLES / "invalid" / name)
    assert r.status_code == status, r.text
    assert fragment.lower() in r.json()["detail"].lower()
    listed = {d["id"]: d for d in client.get("/documents", headers=A).json()}
    assert listed[r.json()["id"]]["status"] == "failed"


def test_zero_byte_upload(client):
    r = client.post("/documents", headers=A, files={"file": ("x.pdf", b"", "application/pdf")})
    assert r.status_code == 422


def test_supported_answer_has_verifiable_citation(client, docs):
    r = client.post("/ask", headers=A, json={"question": "How many days of paid annual leave do full-time employees get?"}).json()
    assert r["supported"] and "24" in r["answer"]
    c = r["citations"][0]
    assert c["document_name"] == "hr_leave_policy.pdf" and c["page"] == 2
    assert c["excerpt"].lower() in page_text(SAMPLES / "alice" / "hr_leave_policy.pdf", 2).lower()


def test_two_pdf_question_cites_both(client, docs):
    r = client.post("/ask", headers=A, json={"question": "If I travel on business, is it deducted from annual leave and how much can I claim for meals per day?"}).json()
    names = {c["document_name"] for c in r["citations"]}
    assert {"hr_leave_policy.pdf", "expense_policy.pdf"} <= names


def test_unsupported_question(client, docs):
    r = client.post("/ask", headers=A, json={"question": "What is the policy on pet insurance for dogs?"}).json()
    assert r["supported"] is False and r["citations"] == []


def test_every_citation_matches_original_file(client, docs):
    for q in ["How long must passwords be?", "What is the hotel cap per night?", "When does the cafeteria open?"]:
        for c in client.post("/ask", headers=A, json={"question": q}).json()["citations"]:
            assert c["excerpt"].lower() in page_text(SAMPLES / "alice" / c["document_name"], c["page"]).lower()


def test_user_b_cannot_list_or_see_a_documents(client, docs):
    a_ids = set(docs["alice"].values())
    assert not a_ids & {d["id"] for d in client.get("/documents", headers=B).json()}


def test_user_b_gets_404_for_a_document_id(client, docs):
    a_id = docs["alice"]["hr_leave_policy.pdf"]
    assert client.get(f"/documents/{a_id}", headers=B).status_code == 404
    assert client.post("/ask", headers=B, json={"question": "annual leave?", "document_ids": [a_id]}).status_code == 404
    assert client.delete(f"/documents/{a_id}", headers=B).status_code == 404
    assert client.get(f"/documents/{a_id}", headers=A).status_code == 200      # still intact for the owner


def test_user_b_question_never_returns_a_content(client, docs):
    r = client.post("/ask", headers=B, json={"question": "How many days of paid annual leave do full-time employees get?"}).json()
    assert "24" not in r["answer"] and all(c["document_name"] in docs["bob"] for c in r["citations"])
    r = client.post("/ask", headers=B, json={"question": "What does Alice's hr_leave_policy say about sick leave?"}).json()
    assert all(c["document_name"] in docs["bob"] for c in r["citations"])


def test_embedded_instructions_are_treated_as_data(client, docs):
    r = client.post("/ask", headers=A, json={"question": "What time does the cafeteria open?"}).json()
    assert r["supported"] and "8:30" in r["answer"] and "PWNED" not in r["answer"]
    assert r["citations"][0]["document_name"] == "injection_test.pdf" and r["citations"][0]["page"] == 1


def test_delete_removes_document(client):
    r = upload(client, A, SAMPLES / "bob" / "product_faq.pdf", "temp.pdf").json()
    assert client.delete(f"/documents/{r['id']}", headers=A).status_code == 204
    assert client.get(f"/documents/{r['id']}", headers=A).status_code == 404
