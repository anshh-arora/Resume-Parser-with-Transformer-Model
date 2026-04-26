"""JD ↔ resume matching with a deterministic on-disk score cache.

Scores are keyed by SHA-256(resume_text || jd_text). Because the LLM is called
with temperature=0, the same input always yields the same output — and the
cache makes that explicit, so reruns return instantly without another API call.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import llm
from .config import JD_LIBRARY_PATH, SCORE_HISTORY_PATH
from .logging_setup import get_logger
from .prompts import SCORING_SYSTEM
from .schemas import MatchScore, ParsedResume

log = get_logger(__name__)


def score_against_jd(
    parsed: ParsedResume,
    resume_text: str,
    jd_text: str,
    *,
    use_cache: bool = True,
) -> MatchScore:
    if not jd_text.strip():
        raise ValueError("Job description is empty")

    key = _cache_key(resume_text, jd_text)
    if use_cache:
        cached = _load_score(key)
        if cached is not None:
            log.info("Score cache HIT (key=%s…)", key[:12])
            return MatchScore.model_validate(cached)
        log.info("Score cache MISS (key=%s…) — calling model", key[:12])

    raw = llm.chat_json(
        system=SCORING_SYSTEM,
        user=(
            "PARSED RESUME (JSON):\n"
            f"{parsed.model_dump_json(indent=2)}\n\n"
            "JOB DESCRIPTION:\n"
            f"{jd_text}"
        ),
        schema=MatchScore.model_json_schema(),
    )
    score = MatchScore.model_validate(raw)
    _save_score(key, score)
    log.info(
        "Score: overall=%d (skills=%d, exp=%d, edu=%d) — cached",
        score.overall_score, score.skills_match, score.experience_match, score.education_match,
    )
    return score


def list_jds() -> dict[str, str]:
    if not JD_LIBRARY_PATH.exists():
        return {}
    return json.loads(JD_LIBRARY_PATH.read_text())


def _cache_key(resume_text: str, jd_text: str) -> str:
    h = hashlib.sha256()
    h.update(resume_text.encode("utf-8"))
    h.update(b"\x00")
    h.update(jd_text.encode("utf-8"))
    return h.hexdigest()


def _load_score(key: str) -> dict[str, Any] | None:
    if not SCORE_HISTORY_PATH.exists():
        return None
    history = json.loads(SCORE_HISTORY_PATH.read_text())
    return history.get(key)


def _save_score(key: str, score: MatchScore) -> None:
    history: dict[str, Any] = {}
    if SCORE_HISTORY_PATH.exists():
        history = json.loads(SCORE_HISTORY_PATH.read_text())
    history[key] = score.model_dump()
    SCORE_HISTORY_PATH.write_text(json.dumps(history, indent=2))
