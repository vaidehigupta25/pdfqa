# PDF Question Answering (with verifiable citations)

Upload several text-based PDFs, ask questions, and get answers that use **only your own documents**, with citations
(document name, PDF page number starting at 1, supporting excerpt). Two demo users are isolated on the server.
Design details: [docs/TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md). Evaluation: [eval/results.md](eval/results.md).

## Setup (clean checkout)

Requires Python 3.11+ (developed on 3.12).

```bash
git clone <repo-url> && cd pdfqa
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # Windows: copy .env.example .env
```

Edit `.env`:

| Variable | Meaning |
|---|---|
| `ALICE_API_KEY`, `BOB_API_KEY` | API keys of the two demo users (placeholders; change freely) |
| `LLM_PROVIDER` | `gemini` (free tier), `groq` (free tier), `ollama` (local), or `extractive` (offline, rule-based, testing only) |
| `LLM_API_KEY`, `LLM_MODEL` | Provider key and model name. Free model names change often - use a current one from your provider |
| `EMBEDDING_BACKEND` | `fastembed` (default; local, free, downloads ~90 MB on first use) or `hash` (offline test stand-in) |
| `MIN_SIMILARITY` | Retrieval gate (default 0.25 for fastembed). Tune with the eval script |

Free LLM key: Gemini at <https://aistudio.google.com> or Groq at <https://console.groq.com>. Note that Gemini's free tier may use
submitted content to improve Google products - the sample PDFs are synthetic. Without a key, use Ollama or `LLM_PROVIDER=extractive`.

## Run

```bash
uvicorn app.main:app --port 8000
```
Open <http://127.0.0.1:8000> (UI) or <http://127.0.0.1:8000/docs> (interactive API docs). The two demo users are created
automatically at startup from `.env`.

**Demo users:** `alice` (key = `ALICE_API_KEY`) and `bob` (key = `BOB_API_KEY`). In the UI, paste a key and press "Use key".
Sample PDFs: `samples/alice/` (4 files incl. `injection_test.pdf`), `samples/bob/` (3 files), `samples/invalid/` (corrupt, truncated, empty, scanned, not-a-PDF).
Regenerate them with `python scripts/make_samples.py`.

## API

All routes except `/health` need an `X-API-Key` header. Identity is resolved on the server; the client never sends a user id.

| Method & path | Purpose | Errors |
|---|---|---|
| `POST /documents` (multipart `file`) | Upload a PDF. Returns `status: processing`, becomes `ready` or `failed` | 401, 413 too large, 415 not a PDF, 422 corrupt / encrypted / empty / scanned |
| `GET /documents` | List the caller's documents with status and error | 401 |
| `GET /documents/{id}` | One document's status | 401, 404 |
| `DELETE /documents/{id}` | Delete a document | 401, 404 |
| `POST /ask` `{"question": "...", "document_ids": [...]?}` | Answer with citations | 401, 404 (unknown/foreign id), 409 (doc not ready), 503 (LLM unavailable) |

```bash
KEY=alice-demo-key-change-me
curl -s -H "X-API-Key: $KEY" -F "file=@samples/alice/hr_leave_policy.pdf" localhost:8000/documents
# {"id":"<uuid>","filename":"hr_leave_policy.pdf","status":"processing","page_count":3}

curl -s -H "X-API-Key: $KEY" localhost:8000/documents
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"question":"How many days of paid annual leave do full-time employees get?"}' localhost:8000/ask
```
Answer shape (values depend on your LLM; replace with your captured response before submitting):
```json
{"answer": "Full-time employees get 24 days of paid annual leave per year.", "supported": true,
 "citations": [{"document_id": "<uuid>", "document_name": "hr_leave_policy.pdf", "page": 2,
                "excerpt": "Full-time employees receive 24 days of paid annual leave per calendar year."}],
 "top_score": 0.71, "provider": "gemini", "model": "..."}
```
Unsupported question -> `{"answer": "The uploaded documents do not contain enough information...", "supported": false, "citations": []}`

Errors:
```bash
curl -s -H "X-API-Key: $KEY" -F "file=@samples/invalid/scanned.pdf" localhost:8000/documents
# HTTP 422 {"detail":"Unsupported: scanned/image-only PDF with no text layer (OCR is not supported).","status":"failed",...}
curl -s -H "X-API-Key: bob-demo-key-change-me" localhost:8000/documents/<alice-doc-id>    # HTTP 404 {"detail":"Document not found"}
```

## Tests and evaluation

```bash
pytest -q                          # 17 offline tests (no key, no download): validation, isolation, citations, injection plumbing
python eval/run_eval.py            # with the server running and your real LLM configured; writes eval/results.md
```
`run_eval.py` uploads the sample PDFs, runs the six required case types (supported, two-PDF, unsupported, invalid upload,
cross-user access, misleading-instructions PDF), checks every citation against the **original PDF file**, and records failures.
Use `--delay 7` (default) to stay under free-tier rate limits.

## Known limitations, incomplete requirements, time, AI usage

- No OCR (optional in the brief): scanned PDFs are rejected with a clear message. Tables / multi-column layouts may extract poorly.
- Brute-force vector search over SQLite is for small collections. Free LLM tiers are rate-limited (the app retries on 429).
- Static API keys are demo-grade authentication. Optional bonuses (hybrid search, history, Docker, OCR) were not implemented.
- Observed failures: *see eval/results.md and TECHNICAL_DESIGN.md section 4 (fill in from your real run).*
- **Time spent:** *TODO: fill in honestly.*
- **AI tools used:** Claude (Anthropic) was used to design the solution and generate code, tests and docs. I reviewed and ran the code and can explain it. *Adjust to what is true for you.*
- Reused libraries: FastAPI, PyMuPDF, fastembed (all-MiniLM-L6-v2), numpy, httpx, reportlab.

## Walkthrough

*TODO: add 3-4 screenshots in `docs/screenshots/` (upload + statuses, supported answer with citations, unsupported answer, error message) and link them here.*
