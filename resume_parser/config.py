from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# override=True so the project .env wins over any stale shell exports
# (e.g. a leftover OLLAMA_HOST=https://ollama.com from a previous session).
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
# When a cloud key is present, default to ollama.com; otherwise assume a local daemon.
OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "https://ollama.com" if OLLAMA_API_KEY else "http://localhost:11434",
)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

JD_LIBRARY_PATH = DATA_DIR / "job_descriptions.json"
SCORE_HISTORY_PATH = DATA_DIR / "score_history.json"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}
