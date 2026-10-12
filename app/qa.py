import re
import numpy as np
from . import config, llm
from .db import get_db
from .embeddings import embed
from .pdf_parser import normalize


def _retrieve(user_id: int, question: str, doc_ids: list[str] | None):
    """Similarity search restricted IN SQL to the caller's own ready documents."""
    sql = ("SELECT c.id, c.document_id, c.page, c.text, c.embedding, d.filename FROM chunks c "
           "JOIN documents d ON d.id=c.document_id "
           "WHERE c.user_id=? AND d.user_id=? AND d.status='ready'")
    params: list = [user_id, user_id]
    if doc_ids:
        sql += f" AND d.id IN ({','.join('?' * len(doc_ids))})"
        params += doc_ids
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    if not rows:
        return [], 0.0
    mat = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    sims = mat @ embed([question])[0]
    top_score = float(sims.max())
    per_doc: dict[str, list] = {}
    for r, s in zip(rows, sims):
        if s >= config.MIN_SIMILARITY:
            per_doc.setdefault(r["document_id"], []).append((float(s), r))
    picked = []
    for items in per_doc.values():          # top-k PER DOCUMENT so one big PDF can't crowd out another
        picked += sorted(items, key=lambda x: -x[0])[:config.TOP_K_PER_DOC]
    picked = sorted(picked, key=lambda x: -x[0])[:config.MAX_EVIDENCE_CHUNKS]
    return picked, top_score


def _page_text(user_id: int, doc_id: str, page: int) -> str:
    with get_db() as db:
        row = db.execute("SELECT text FROM pages WHERE document_id=? AND user_id=? AND page=?",
                         (doc_id, user_id, page)).fetchone()
    return row["text"] if row else ""


def _best_sentence(chunk_text: str, answer: str) -> str:
    """Fallback excerpt chosen by the server: the chunk sentence most similar to the answer."""
    ans = llm._content_words(answer)
    sents = re.split(r"(?<=[.!?])\s+", chunk_text)
    return max(sents, key=lambda s: len(ans & llm._content_words(s)))[:config.MAX_EXCERPT_CHARS]


def _verified_excerpt(quote: str, page_text: str) -> str | None:
    """Return the exact slice of the stored page text matching the LLM quote, or None."""
    q = normalize(quote)
    if len(q) < 8:
        return None
    idx = page_text.lower().find(q.lower())
    if idx < 0:
        return None
    return page_text[idx: idx + min(len(q), config.MAX_EXCERPT_CHARS)]


def _not_found(top_score: float) -> dict:
    return {"answer": config.NOT_FOUND_MESSAGE, "supported": False, "citations": [],
            "top_score": round(top_score, 3), "provider": config.LLM_PROVIDER, "model": config.LLM_MODEL}


def ask(user_id: int, question: str, doc_ids: list[str] | None) -> dict:
    picked, top_score = _retrieve(user_id, question, doc_ids)
    if not picked:                                       # layer 1: retrieval gate (no LLM call)
        return _not_found(top_score)
    evidence = []
    for i, (_, r) in enumerate(picked, 1):
        evidence.append({"alias": f"C{i}", "doc_id": r["document_id"], "doc_name": r["filename"],
                         "page": r["page"], "text": r["text"]})
    by_alias = {e["alias"]: e for e in evidence}

    result = llm.generate(question, evidence)
    if not result.get("supported"):                      # layer 2: model says unsupported
        return _not_found(top_score)

    citations, seen = [], set()
    for c in result.get("citations") or []:
        e = by_alias.get(str(c.get("chunk_id", "")).strip("[] "))
        if not e:
            continue                                     # ignore invented/unknown chunk ids
        page_text = _page_text(user_id, e["doc_id"], e["page"])
        excerpt = _verified_excerpt(str(c.get("quote", "")), page_text) or _best_sentence(e["text"], result.get("answer", ""))
        key = (e["doc_id"], e["page"], excerpt)
        if key in seen:
            continue
        seen.add(key)
        citations.append({"document_id": e["doc_id"], "document_name": e["doc_name"],
                          "page": e["page"], "excerpt": excerpt})
    answer = str(result.get("answer", "")).strip()
    if not citations or not answer:                      # layer 3: no valid citation => no answer
        return _not_found(top_score)
    return {"answer": answer, "supported": True, "citations": citations,
            "top_score": round(top_score, 3), "provider": config.LLM_PROVIDER, "model": config.LLM_MODEL}
