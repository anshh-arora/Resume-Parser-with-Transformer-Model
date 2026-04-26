from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_resume_pdf() -> Path:
    pdf = FIXTURES / "sample_resume.pdf"
    assert pdf.exists(), f"Missing test fixture: {pdf}"
    return pdf


@pytest.fixture
def fake_parsed_payload() -> dict:
    return {
        "contact": {
            "name": "Ansh Arora",
            "email": "ansharora.cs@gmail.com",
            "phone": "+91 7217671081",
            "location": None,
            "linkedin": "LinkedIn",
            "github": "GitHub",
        },
        "summary": "AI Engineer with production experience in Agentic AI systems.",
        "skills": [
            "Python", "LangChain", "LangGraph", "Ollama", "RAG", "MCP",
            "AWS", "Docker", "PostgreSQL", "MongoDB", "FastAPI", "Gradio",
        ],
        "education": [{
            "institution": "Lingaya's Vidyapeeth",
            "degree": "Bachelor of Computer Application",
            "field_of_study": "Computer Application",
            "graduation_year": "2025",
            "grade": None,
        }],
        "experience": [{
            "company": "Smartworks",
            "position": "Junior AI Engineer",
            "duration": "July 2025 – Present",
            "description": "Built production agentic SQL chatbot using LangGraph and Ollama.",
        }],
        "projects": [],
        "certifications": ["Prompt Engineering — Coursera"],
        "achievements": ["Winner, Corporate Hackathon (Smartworks)"],
    }


@pytest.fixture
def fake_score_payload() -> dict:
    return {
        "overall_score": 92,
        "skills_match": 95,
        "experience_match": 88,
        "education_match": 90,
        "matched_skills": ["LangGraph", "Ollama", "RAG", "Python", "AWS", "Docker"],
        "missing_skills": ["Airflow"],
        "strengths": [
            "Direct experience deploying LangGraph agents to production.",
            "Strong AWS + Docker deployment background.",
        ],
        "gaps": ["Limited years of post-degree experience."],
        "verdict": "Strong fit — recommend advancing to technical screen.",
    }
