import hashlib
from fastapi import Header, HTTPException
from . import config
from .db import get_db


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def seed_users():
    """Create the two demo users from environment config (keys stored hashed)."""
    with get_db() as db:
        for name, key in config.DEMO_USERS.items():
            db.execute("INSERT INTO users(name, api_key_hash) VALUES(?,?) "
                       "ON CONFLICT(name) DO UPDATE SET api_key_hash=excluded.api_key_hash",
                       (name, hash_key(key)))


def current_user(x_api_key: str = Header(default="")) -> dict:
    """Identity is resolved on the server from the API key. The client never sends a user id."""
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key header")
    with get_db() as db:
        row = db.execute("SELECT id, name FROM users WHERE api_key_hash=?", (hash_key(x_api_key),)).fetchone()
    if not row:
        raise HTTPException(401, "Invalid API key")
    return {"id": row["id"], "name": row["name"]}
