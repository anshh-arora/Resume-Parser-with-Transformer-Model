from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from resume_parser import scoring
from resume_parser.schemas import MatchScore, ParsedResume


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    """Redirect score history to a per-test file so tests don't pollute real data."""
    history_path = tmp_path / "score_history.json"
    monkeypatch.setattr(scoring, "SCORE_HISTORY_PATH", history_path)
    yield history_path


def test_score_against_jd_persists_and_caches(fake_parsed_payload, fake_score_payload, isolated_history):
    parsed = ParsedResume.model_validate(fake_parsed_payload)
    resume_text = "Ansh Arora — AI Engineer at Smartworks…"
    jd = "We need an AI Engineer with LangGraph and Ollama experience."

    with patch("resume_parser.scoring.llm.chat_json", return_value=fake_score_payload) as mock_chat:
        first = scoring.score_against_jd(parsed, resume_text, jd)
        second = scoring.score_against_jd(parsed, resume_text, jd)

    assert isinstance(first, MatchScore)
    assert first.overall_score == fake_score_payload["overall_score"]
    assert first == second
    # Second call should hit the cache, so the model is only invoked once.
    assert mock_chat.call_count == 1

    # And the score is on disk.
    history = json.loads(isolated_history.read_text())
    assert len(history) == 1


def test_score_cache_keyed_by_resume_and_jd(fake_parsed_payload, fake_score_payload, isolated_history):
    parsed = ParsedResume.model_validate(fake_parsed_payload)
    with patch("resume_parser.scoring.llm.chat_json", return_value=fake_score_payload) as mock_chat:
        scoring.score_against_jd(parsed, "resume A", "jd 1")
        scoring.score_against_jd(parsed, "resume A", "jd 2")
        scoring.score_against_jd(parsed, "resume B", "jd 1")
    # Three distinct (resume, jd) pairs → three real calls.
    assert mock_chat.call_count == 3


def test_score_against_jd_rejects_empty_jd(fake_parsed_payload):
    parsed = ParsedResume.model_validate(fake_parsed_payload)
    with pytest.raises(ValueError):
        scoring.score_against_jd(parsed, "resume text", "   ")


def test_list_jds_reads_library(monkeypatch, tmp_path):
    library = tmp_path / "jds.json"
    library.write_text(json.dumps({"Role A": "desc"}))
    monkeypatch.setattr(scoring, "JD_LIBRARY_PATH", library)
    assert scoring.list_jds() == {"Role A": "desc"}
