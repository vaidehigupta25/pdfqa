import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, qa
from .auth import current_user, seed_users
from .chunker import chunk_page
from .db import get_db, init_db
from .embeddings import embed
from .llm import LLMError
from .pdf_parser import PdfError, extract_pages

log = logging.getLogger("pdfqa")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_users()
    yield


app = FastAPI(title="PDF Q&A", lifespan=lifespan)


def _doc_dict(r) -> dict:
    return {"id": r["id"], "filename": r["filename"], "status": r["status"],
            "error": r["error"], "page_count": r["page_count"], "created_at": r["created_at"]}


def _owned_doc(db, doc_id: str, user_id: int):
    """Ownership check in SQL. Missing and foreign documents are indistinguishable (404)."""
    row = db.execute("SELECT * FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return row


def _process_document(doc_id: str, user_id: int):
    """Background job: chunk (within pages) -> embed -> store. Updates status."""
    try:
        with get_db() as db:
            pages = db.execute("SELECT page, text FROM pages WHERE document_id=? AND user_id=? ORDER BY page",
                               (doc_id, user_id)).fetchall()
        items = [(p["page"], c) for p in pages for c in chunk_page(p["text"])]
        vecs = embed([c for _, c in items])
        with get_db() as db:
            db.executemany("INSERT INTO chunks(document_id,user_id,page,text,embedding) VALUES(?,?,?,?,?)",
                           [(doc_id, user_id, pg, txt, v.tobytes()) for (pg, txt), v in zip(items, vecs)])
            db.execute("UPDATE documents SET status='ready' WHERE id=? AND user_id=?", (doc_id, user_id))
    except Exception as e:
        log.exception("processing failed")
        with get_db() as db:
            db.execute("UPDATE documents SET status='failed', error=? WHERE id=? AND user_id=?",
                       (f"Processing failed: {e}", doc_id, user_id))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents", status_code=201)
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...), user=Depends(current_user)):
    filename = os.path.basename(file.filename or "upload.pdf")[:200] or "upload.pdf"
    doc_id = str(uuid.uuid4())
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    error = None
    if len(data) > config.MAX_UPLOAD_BYTES:
        error = PdfError(413, f"File too large (limit {config.MAX_UPLOAD_BYTES // 1024 // 1024} MB).")
    elif not data:
        error = PdfError(422, "Empty file: 0 bytes uploaded.")
    else:
        try:
            pages = extract_pages(data)
        except PdfError as e:
            error = e
    if error:                                            # record failure so it is visible in the document list
        with get_db() as db:
            db.execute("INSERT INTO documents(id,user_id,filename,status,error) VALUES(?,?,?,'failed',?)",
                       (doc_id, user["id"], filename, error.message))
        return JSONResponse(status_code=error.status,
                            content={"detail": error.message, "id": doc_id, "filename": filename, "status": "failed"})
    path = config.UPLOAD_DIR / f"{doc_id}.pdf"          # never use the client's filename on disk
    path.write_bytes(data)
    with get_db() as db:
        db.execute("INSERT INTO documents(id,user_id,filename,status,page_count,file_path) VALUES(?,?,?,'processing',?,?)",
                   (doc_id, user["id"], filename, len(pages), str(path)))
        db.executemany("INSERT INTO pages(document_id,user_id,page,text) VALUES(?,?,?,?)",
                       [(doc_id, user["id"], i, t) for i, t in enumerate(pages, 1)])
    background.add_task(_process_document, doc_id, user["id"])
    return {"id": doc_id, "filename": filename, "status": "processing", "page_count": len(pages)}


@app.get("/documents")
def list_documents(user=Depends(current_user)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM documents WHERE user_id=? ORDER BY created_at DESC, rowid DESC", (user["id"],)).fetchall()
    return [_doc_dict(r) for r in rows]


@app.get("/documents/{doc_id}")
def get_document(doc_id: str, user=Depends(current_user)):
    with get_db() as db:
        return _doc_dict(_owned_doc(db, doc_id, user["id"]))


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, user=Depends(current_user)):
    with get_db() as db:
        row = _owned_doc(db, doc_id, user["id"])
        for t in ("chunks", "pages"):
            db.execute(f"DELETE FROM {t} WHERE document_id=? AND user_id=?", (doc_id, user["id"]))
        db.execute("DELETE FROM documents WHERE id=? AND user_id=?", (doc_id, user["id"]))
    if row["file_path"]:
        Path(row["file_path"]).unlink(missing_ok=True)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = None


@app.post("/ask")
def ask(req: AskRequest, user=Depends(current_user)):
    if req.document_ids:
        with get_db() as db:
            for d in req.document_ids:
                if _owned_doc(db, d, user["id"])["status"] != "ready":
                    raise HTTPException(409, f"Document {d} is not ready (still processing or failed).")
    try:
        return qa.ask(user["id"], req.question.strip(), req.document_ids)
    except LLMError as e:
        raise HTTPException(503, f"Language model unavailable: {e}")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
