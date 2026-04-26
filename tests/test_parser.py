from __future__ import annotations

from unittest.mock import patch

from resume_parser.parser import (
    _ground_in_source,
    _looks_like_garbage_project,
    _rescue_certs_and_achievements,
    parse_resume,
    parse_text,
)
from resume_parser.schemas import ParsedResume


def test_parse_resume_validates_llm_output(sample_resume_pdf, fake_parsed_payload):
    with patch("resume_parser.parser.llm.chat_json", return_value=fake_parsed_payload) as mock_chat:
        parsed = parse_resume(sample_resume_pdf)
    assert isinstance(parsed, ParsedResume)
    assert parsed.contact.name == "Ansh Arora"
    mock_chat.assert_called_once()
    # The prompt should carry the extracted resume text, not just a path.
    call_kwargs = mock_chat.call_args.kwargs
    assert "Resume text:" in call_kwargs["user"]
    assert "Smartworks" in call_kwargs["user"]


def test_parse_text_rejects_empty():
    import pytest
    with pytest.raises(ValueError):
        parse_text("   \n  ")


# ── Source grounding tests ───────────────────────────────────────────────

def test_grounding_drops_linkedin_handle_without_url():
    """If the model returns just a handle like 'ansharora.cs', it must be nulled."""
    payload = {"contact": {"linkedin": "ansharora.cs"}}
    result = _ground_in_source(payload, "Some resume text with LinkedIn hyperlink")
    assert result["contact"]["linkedin"] is None


def test_grounding_keeps_full_linkedin_url():
    """A full LinkedIn URL that appears in the source should be kept."""
    payload = {"contact": {"linkedin": "https://linkedin.com/in/ansharora-cs"}}
    source = "Find me at linkedin.com/in/ansharora-cs"
    result = _ground_in_source(payload, source)
    assert result["contact"]["linkedin"] == "https://linkedin.com/in/ansharora-cs"


def test_grounding_drops_bare_github_domain():
    """Bare 'https://github.com' (no handle) must be dropped."""
    payload = {"contact": {"github": "https://github.com"}}
    result = _ground_in_source(payload, "Resume with GitHub link text")
    assert result["contact"]["github"] is None


def test_grounding_drops_github_without_url():
    """A handle like 'ansharora' without github.com/ prefix should be dropped."""
    payload = {"contact": {"github": "ansharora"}}
    result = _ground_in_source(payload, "Resume with GitHub link text")
    assert result["contact"]["github"] is None


def test_grounding_keeps_full_github_url():
    """A full GitHub URL in source should be kept."""
    payload = {"contact": {"github": "https://github.com/ansharora"}}
    source = "Projects at github.com/ansharora"
    result = _ground_in_source(payload, source)
    assert result["contact"]["github"] == "https://github.com/ansharora"


# ── Garbage project filter tests ────────────────────────────────────────

def test_garbage_filter_catches_repeating_numbers():
    p = {"name": "certifications_achievements_1_2_3_4_5", "description": None, "technologies": []}
    assert _looks_like_garbage_project(p) is True


def test_garbage_filter_catches_section_headers():
    p = {"name": "Certifications & Achievements", "description": None, "technologies": []}
    assert _looks_like_garbage_project(p) is True


def test_garbage_filter_allows_real_projects():
    p = {"name": "LLM Complaint System", "description": "Built a chatbot", "technologies": ["Python"]}
    assert _looks_like_garbage_project(p) is False


# ── Cert/achievement rescue tests ───────────────────────────────────────

def test_rescue_moves_certs_from_projects():
    payload = {
        "projects": [
            {"name": "Real Project", "description": "A project", "technologies": ["Python"]},
            {"name": "Prompt Engineering Certification", "description": None, "technologies": []},
        ],
        "certifications": [],
        "achievements": [],
    }
    result = _rescue_certs_and_achievements(payload)
    assert len(result["projects"]) == 1
    assert result["projects"][0]["name"] == "Real Project"
    assert "Prompt Engineering Certification" in result["certifications"]


def test_rescue_moves_achievements_from_projects():
    payload = {
        "projects": [
            {"name": "Winner, Corporate Hackathon", "description": "Built ML tool", "technologies": []},
        ],
        "certifications": [],
        "achievements": [],
    }
    result = _rescue_certs_and_achievements(payload)
    assert len(result["projects"]) == 0
    assert "Built ML tool" in result["achievements"]
