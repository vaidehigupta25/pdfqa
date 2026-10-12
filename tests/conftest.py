import os
import tempfile
from pathlib import Path

# Offline test configuration: must be set BEFORE the app is imported.
os.environ.update({
    "DATA_DIR": tempfile.mkdtemp(prefix="pdfqa_test_"),
    "EMBEDDING_BACKEND": "hash", "LLM_PROVIDER": "extractive",
    "ALICE_API_KEY": "test-alice-key", "BOB_API_KEY": "test-bob-key",
})
os.environ.pop("MIN_SIMILARITY", None)

import pytest
from fastapi.testclient import TestClient
from app.main import app

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
A, B = {"X-API-Key": "test-alice-key"}, {"X-API-Key": "test-bob-key"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def upload(client, headers, path: Path, name: str | None = None):
    return client.post("/documents", headers=headers, files={"file": (name or path.name, path.read_bytes(), "application/pdf")})


@pytest.fixture(scope="session")
def docs(client):
    """Alice uploads her 4 PDFs, Bob his 3. Returns {filename: id} per user."""
    out = {"alice": {}, "bob": {}}
    for user, hdr in (("alice", A), ("bob", B)):
        for p in sorted((SAMPLES / user).glob("*.pdf")):
            r = upload(client, hdr, p)
            assert r.status_code == 201, r.text
            out[user][p.name] = r.json()["id"]
    return out
