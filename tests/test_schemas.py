from __future__ import annotations

import pytest
from pydantic import ValidationError

from resume_parser.schemas import MatchScore, ParsedResume


def test_parsed_resume_round_trip(fake_parsed_payload):
    parsed = ParsedResume.model_validate(fake_parsed_payload)
    assert parsed.contact.name == "Ansh Arora"
    assert "LangGraph" in parsed.skills
    assert parsed.education[0].institution.startswith("Lingaya")


def test_parsed_resume_tolerates_missing_fields():
    minimal = {"contact": {"name": "Test"}}
    parsed = ParsedResume.model_validate(minimal)
    assert parsed.contact.name == "Test"
    assert parsed.skills == []
    assert parsed.experience == []


def test_match_score_clamps_invalid_values(fake_score_payload):
    score = MatchScore.model_validate(fake_score_payload)
    assert 0 <= score.overall_score <= 100

    bad = dict(fake_score_payload, overall_score=150)
    with pytest.raises(ValidationError):
        MatchScore.model_validate(bad)
