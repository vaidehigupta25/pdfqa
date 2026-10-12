"""Look inside the database: pages, chunks, embeddings, and retrieval done step by step.
Run from the project folder:
    python scripts/inspect_data.py
    python scripts/inspect_data.py --user bob --file product_faq.pdf --question "How many Ethernet ports?"
The server does not need to be running."""
import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.chunker import chunk_page
from app.db import get_db
from app.embeddings import embed

ap = argparse.ArgumentParser()
ap.add_argument("--user", default="alice")
ap.add_argument("--file", default="hr_leave_policy.pdf")
ap.add_argument("--question", default="How many days of annual leave do employees get?")
a = ap.parse_args()


def title(text):
    print("\n" + "=" * 72 + f"\n{text}\n" + "=" * 72)


with get_db() as db:
    user = db.execute("SELECT id FROM users WHERE name=?", (a.user,)).fetchone()
    if not user:
        sys.exit(f"No user named {a.user}. Start the server once so demo users are created.")
    uid = user["id"]

    # ---------------------------------------------------------------- 1
    title(f"1. {a.user}'s documents (table: documents) and how many chunks each has (table: chunks)")
    rows = db.execute("""SELECT d.filename, d.status, d.page_count, COUNT(c.id) AS chunks
                         FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                         WHERE d.user_id = ? GROUP BY d.id ORDER BY d.created_at""", (uid,)).fetchall()
    for r in rows:
        print(f"  {r['filename']:32} status={r['status']:10} pages={r['page_count']}  chunks={r['chunks']}")

    doc = db.execute("SELECT id FROM documents WHERE user_id=? AND filename=? AND status='ready' ORDER BY created_at DESC",
                     (uid, a.file)).fetchone()
    if not doc:
        sys.exit(f"\nNo READY document called {a.file} for {a.user}. Pick one from the list above with --file.")

    # ---------------------------------------------------------------- 2
    title(f"2. Pages (table: pages) and chunks (table: chunks) of {a.file}")
    pages = db.execute("SELECT page, text FROM pages WHERE document_id=? AND user_id=? ORDER BY page", (doc["id"], uid)).fetchall()
    chunks = db.execute("SELECT id, page, text, embedding FROM chunks WHERE document_id=? AND user_id=? ORDER BY id", (doc["id"], uid)).fetchall()
    for p in pages:
        print(f"\n--- PAGE {p['page']}  ({len(p['text'])} characters of cleaned text) ---")
        print(p["text"])
        for c in [c for c in chunks if c["page"] == p["page"]]:
            print(f"    >>> CHUNK id={c['id']}  page={c['page']}  length={len(c['text'])} characters")
    print("\nNote: a chunk always belongs to exactly one page. Short pages stay as one chunk.")

    # ---------------------------------------------------------------- 3
    title("3. What an embedding looks like (first chunk of this document)")
    c0 = chunks[0]
    vec = np.frombuffer(c0["embedding"], dtype=np.float32)
    print(f"  Chunk text      : {c0['text'][:90]}...")
    print(f"  Stored as       : a BLOB of {len(c0['embedding'])} bytes in the 'embedding' column")
    print(f"  Decoded         : {len(vec)} numbers (float32, 4 bytes each = {len(vec) * 4} bytes)")
    print(f"  First 8 numbers : {np.round(vec[:8], 4).tolist()}")
    print(f"  Vector length   : {np.linalg.norm(vec):.4f}   (normalised to 1, so dot product = cosine similarity)")
    print(f"  Embedding model : {config.EMBEDDING_BACKEND} / {config.EMBEDDING_MODEL}")

# ---------------------------------------------------------------- 4
title("4. Chunking demo on a LONG page (your sample pages are short, so we fake a long one)")
long_text = " ".join(f"Sentence {i:02d} is about leave rules and takes up roughly sixty characters." for i in range(1, 41))
parts = chunk_page(long_text)
print(f"  Fake page: {len(long_text)} characters, 40 numbered sentences. Settings: size={config.CHUNK_SIZE}, overlap={config.CHUNK_OVERLAP}")
for i, p in enumerate(parts, 1):
    nums = [int(n) for n in re.findall(r"Sentence (\d+)", p)]
    print(f"  Chunk {i}: {len(p):4} characters, sentences {nums[0]:02d} to {nums[-1]:02d}")
print("  Look at the numbers: the last sentences of one chunk reappear at the start of the next (overlap),")
print("  so a fact that sits on a boundary is still fully inside at least one chunk.")

# ---------------------------------------------------------------- 5
title(f"5. Retrieval by hand for the question: {a.question!r}")
qv = embed([a.question])[0]
print(f"  The question became {len(qv)} numbers too. First 6: {np.round(qv[:6], 4).tolist()}")
with get_db() as db:
    allc = db.execute("""SELECT c.page, c.text, c.embedding, d.filename FROM chunks c JOIN documents d ON d.id=c.document_id
                         WHERE c.user_id=? AND d.user_id=? AND d.status='ready'""", (uid, uid)).fetchall()
scored = sorted(((float(np.frombuffer(r["embedding"], dtype=np.float32) @ qv), r) for r in allc), key=lambda x: -x[0])
print(f"  Score = dot product of question numbers and chunk numbers (cosine similarity). Gate: MIN_SIMILARITY = {config.MIN_SIMILARITY}")
print(f"  ALL {len(scored)} of {a.user}'s chunks, best first:\n")
for s, r in scored:
    mark = "PASS" if s >= config.MIN_SIMILARITY else "below gate"
    print(f"   {s:6.3f}  {mark:10}  {r['filename']:28} page {r['page']}   {r['text'][:55]}...")
print("\n  The app keeps the PASS chunks, takes the top 3 per document (max 8 overall), and sends only those to the LLM.")

# ---------------------------------------------------------------- 6
title("6. Meaning, not keywords (only meaningful with the real fastembed model)")
sents = ["Employees get 24 days of paid vacation.", "How many days of annual leave do I have?", "Passwords must be 14 characters long.", "The cafeteria opens at 8:30 AM."]
vs = embed(sents)
for i in range(1, len(sents)):
    print(f"   {float(vs[0] @ vs[i]):6.3f}   {sents[0]!r}  vs  {sents[i]!r}")
print("  Expect the 'annual leave' question to score much higher against the vacation sentence than the others,")
print("  even though it shares almost no words ('vacation' vs 'annual leave').")