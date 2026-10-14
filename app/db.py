import sqlite3
from contextlib import contextmanager
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  api_key_hash TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  filename TEXT NOT NULL,
  status TEXT NOT NULL,            -- processing | ready | failed
  error TEXT,
  page_count INTEGER DEFAULT 0,
  file_path TEXT,
  ocr_used INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS pages(
  document_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  page INTEGER NOT NULL,           -- 1-based
  text TEXT NOT NULL,
  PRIMARY KEY(document_id, page));
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  page INTEGER NOT NULL,
  text TEXT NOT NULL,
  embedding BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS idx_docs_user ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON chunks(user_id, document_id);
"""


@contextmanager
def get_db():
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        # migrate databases created before the OCR flag existed
        cols = [r["name"] for r in db.execute("PRAGMA table_info(documents)")]
        if "ocr_used" not in cols:
            db.execute("ALTER TABLE documents ADD COLUMN ocr_used INTEGER DEFAULT 0")
