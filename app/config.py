import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
MAX_PAGES = int(os.getenv("MAX_PAGES", "300"))

DEMO_USERS = {
    "alice": os.getenv("ALICE_API_KEY", "alice-demo-key-change-me"),
    "bob": os.getenv("BOB_API_KEY", "bob-demo-key-change-me"),
}

EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "fastembed")  # fastembed | hash
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MIN_SIMILARITY = float(os.getenv("MIN_SIMILARITY", "0.25" if EMBEDDING_BACKEND == "fastembed" else "0.12"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # gemini | groq | ollama | extractive
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
_DEFAULTS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-latest"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "ollama": ("http://localhost:11434/v1", "llama3.2"),
    "extractive": ("", "rule-based"),
}
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or _DEFAULTS.get(LLM_PROVIDER, ("", ""))[0]
LLM_MODEL = LLM_MODEL or _DEFAULTS.get(LLM_PROVIDER, ("", ""))[1]

TOP_K_PER_DOC = 3
MAX_EVIDENCE_CHUNKS = 8
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
MAX_EXCERPT_CHARS = 300
NOT_FOUND_MESSAGE = "The uploaded documents do not contain enough information to answer this question."
