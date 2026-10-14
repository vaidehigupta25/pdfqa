"""Diagnose the LLM connection from your .env: lists the models your key can use and times one tiny request.
Usage (from the project folder, venv active):
    python scripts/check_llm.py                      # test the model in .env
    python scripts/check_llm.py --model SOME-NAME    # try another model name without editing .env
Never prints your API key."""
import argparse
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config

ap = argparse.ArgumentParser()
ap.add_argument("--model", default=None)
ap.add_argument("--timeout", type=float, default=60)
args = ap.parse_args()

model = args.model or config.LLM_MODEL
headers = {"Authorization": f"Bearer {config.LLM_API_KEY or 'ollama'}"}
print(f"Provider : {config.LLM_PROVIDER}")
print(f"Base URL : {config.LLM_BASE_URL}")
print(f"Model    : {model}")
print(f"API key  : {'set (' + str(len(config.LLM_API_KEY)) + ' characters)' if config.LLM_API_KEY else 'NOT SET - check LLM_API_KEY in .env'}")

SKIP = ("embed", "tts", "image", "imagen", "veo", "whisper", "guard", "audio", "live", "aqa", "transcri", "robotics", "computer-use", "orpheus", "safeguard")
print("\n1) Chat models available to this key:")
try:
    r = httpx.get(f"{config.LLM_BASE_URL}/models", headers=headers, timeout=20)
    if r.status_code == 200:
        ids = sorted({m.get("id", "").replace("models/", "") for m in r.json().get("data", [])})
        chat = [i for i in ids if i and not any(s in i.lower() for s in SKIP)]
        for i in chat:
            print("    ", i)
        if model.replace("models/", "") not in ids:
            print(f"\n   NOTE: '{model}' is not in the list above. Aliases ending in -latest may still work; a plain wrong name will not.")
    else:
        print(f"   HTTP {r.status_code}: {r.text[:300]}")
        if r.status_code in (401, 403):
            print("   -> the API key is wrong, expired, or not enabled.")
except httpx.HTTPError as e:
    print(f"   Could not reach {config.LLM_BASE_URL}: {type(e).__name__}: {e}")
    print("   -> check your internet connection, VPN/proxy or firewall.")

print(f"\n2) One tiny test request to '{model}' (timeout {args.timeout:.0f} s):")
t0 = time.time()
try:
    r = httpx.post(f"{config.LLM_BASE_URL}/chat/completions", headers=headers, timeout=args.timeout,
                   json={"model": model, "temperature": 0, "messages": [{"role": "user", "content": "Reply with the single word OK."}]})
    print(f"   HTTP {r.status_code} after {time.time() - t0:.1f} s")
    if r.status_code == 200:
        print("   Reply:", (r.json()["choices"][0]["message"]["content"] or "")[:80])
        print("\nRESULT: this model works. Put it in .env as LLM_MODEL=" + model + " and restart uvicorn.")
        if time.time() - t0 > 20:
            print("WARNING: slower than 20 s for a trivial request - pick a faster (lite/instant/8b) model.")
    else:
        print("   Provider said:", r.text[:500])
        hints = {400: "bad request or wrong model name", 401: "wrong API key", 403: "key not allowed for this model",
                 404: "model name does not exist - copy one from the list above", 429: "quota / rate limit - see the message above"}
        print("   ->", hints.get(r.status_code, "see the provider message above"))
except httpx.TimeoutException:
    print(f"   TIMEOUT after {time.time() - t0:.0f} s: the server did not answer a trivial request in time.")
    print("   -> try a different (lighter) model with --model, or a different provider.")
except httpx.HTTPError as e:
    print(f"   {type(e).__name__}: {e}")