import re
from . import config


def chunk_page(text: str, size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    """Split ONE page into chunks. Chunks never cross page boundaries (keeps page citations exact)."""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    sentences = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        while len(s) > size:                       # hard-split very long "sentences"
            sentences.append(s[:size]); s = s[size:]
        if s:
            sentences.append(s)
    chunks, cur = [], []
    for s in sentences:
        if cur and len(" ".join(cur)) + len(s) + 1 > size:
            chunks.append(" ".join(cur))
            keep, total = [], 0                    # carry trailing sentences as overlap
            for prev in reversed(cur):
                if total + len(prev) > overlap:
                    break
                keep.insert(0, prev); total += len(prev)
            cur = keep
        cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    return chunks
