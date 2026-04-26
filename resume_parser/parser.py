"""Resume → structured JSON, end to end.

Four layers of hallucination defense:
  1. Grammar-constrained generation — Pydantic schema is passed to Ollama's
     `format` param, which forces output to match the shape exactly.
  2. Sanitization — drop list entries that don't fit (e.g. strings where an
     object is expected), filter projects that look like model leakage.
  3. Source grounding — null out URLs / emails that don't actually appear in
     the resume text. This is what catches `https://github.com` (bare domain).
  4. Section rescue — detect certifications/achievements that the model
     incorrectly stuffed into projects and move them to the right arrays.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import llm
from .extractors import extract_text
from .logging_setup import get_logger
from .prompts import PARSER_SYSTEM
from .schemas import ParsedResume

log = get_logger(__name__)

_LIST_OF_OBJECTS = {"education", "experience", "projects"}
_LIST_OF_STRINGS = {"skills", "certifications", "achievements"}


def parse_resume(file_path: str | Path) -> ParsedResume:
    text = extract_text(file_path)
    return parse_text(text)


def parse_text(resume_text: str) -> ParsedResume:
    if not resume_text.strip():
        raise ValueError("Resume text is empty")

    log.info("Parsing resume (%d chars) with the LLM…", len(resume_text))
    raw = llm.chat_json(
        system=PARSER_SYSTEM,
        user=f"Resume text:\n\n{resume_text}",
        schema=ParsedResume.model_json_schema(),
    )

    cleaned = _sanitize(raw)
    cleaned = _rescue_certs_and_achievements(cleaned)
    cleaned = _ground_in_source(cleaned, resume_text)
    parsed = ParsedResume.model_validate(cleaned)
    log.info(
        "Parsed: name=%r, %d skills, %d experience, %d education, "
        "%d projects, %d certs, %d achievements",
        parsed.contact.name,
        len(parsed.skills),
        len(parsed.experience),
        len(parsed.education),
        len(parsed.projects),
        len(parsed.certifications),
        len(parsed.achievements),
    )
    return parsed


def _sanitize(payload: Any) -> dict:
    """Coerce a possibly-sloppy LLM payload into the shape ParsedResume expects."""
    if not isinstance(payload, dict):
        log.warning("LLM did not return a JSON object; got %s", type(payload).__name__)
        return {}

    cleaned = dict(payload)

    for key in _LIST_OF_OBJECTS:
        items = cleaned.get(key)
        if not isinstance(items, list):
            cleaned[key] = []
            continue
        kept: list[dict] = []
        for item in items:
            if isinstance(item, dict):
                kept.append(item)
            elif isinstance(item, str) and item.strip():
                kept.append(_wrap_string(key, item))
        if key == "projects":
            kept = [p for p in kept if not _looks_like_garbage_project(p)]
        if len(kept) != len(items):
            log.warning("Sanitized %r: kept %d / %d entries", key, len(kept), len(items))
        cleaned[key] = kept

    for key in _LIST_OF_STRINGS:
        items = cleaned.get(key)
        if not isinstance(items, list):
            cleaned[key] = []
            continue
        cleaned[key] = [
            str(x).strip() for x in items
            if isinstance(x, (str, int, float)) and str(x).strip()
        ]

    if not isinstance(cleaned.get("contact"), dict):
        cleaned["contact"] = {}

    return cleaned


def _looks_like_garbage_project(p: dict) -> bool:
    """Detect model-leaked entries like 'certifications_achievements_1_2_3_...'."""
    name = (p.get("name") or "").strip()
    name_lower = name.lower()
    desc = p.get("description")
    techs = p.get("technologies") or []

    # Repeating "_N" patterns are a giveaway of a small model enumerating tokens.
    if re.search(r"(_\d+){3,}", name):
        log.warning("Garbage project (repeating _N): %r", name)
        return True
    # No description AND no technologies AND a long underscored name → almost certainly garbage.
    if not desc and not techs and "_" in name and len(name) > 40:
        log.warning("Garbage project (long underscored name): %r", name)
        return True
    # Empty everything.
    if not name and not desc and not techs:
        return True
    # Section header leaked as a project name (e.g. "certifications & achievements").
    section_keywords = {"certification", "achievement", "award", "honor", "education"}
    if not desc and not techs and any(kw in name_lower for kw in section_keywords):
        log.warning("Garbage project (section header): %r", name)
        return True
    return False


def _rescue_certs_and_achievements(payload: dict) -> dict:
    """Move certifications/achievements that the model incorrectly placed in projects.

    Small models often dump everything into the projects array.  Detect entries
    whose name contains 'certif' or 'achieve' keywords and has no real
    description or technologies, then move the text to the correct top-level key.
    """
    projects = payload.get("projects", [])
    certs = list(payload.get("certifications", []))
    achieves = list(payload.get("achievements", []))
    kept_projects: list[dict] = []

    for p in projects:
        name = (p.get("name") or "").strip()
        desc = (p.get("description") or "").strip()
        techs = p.get("technologies") or []
        name_lower = name.lower()

        # If name looks like a cert/achievement AND there's no real project content
        if not techs and ("certif" in name_lower or "award" in name_lower):
            entry = desc if desc else name
            if entry and entry not in certs:
                certs.append(entry)
                log.info("Rescued certification from projects: %r", entry)
            continue
        if not techs and ("winner" in name_lower or "hackathon" in name_lower or "achiev" in name_lower):
            entry = desc if desc else name
            if entry and entry not in achieves:
                achieves.append(entry)
                log.info("Rescued achievement from projects: %r", entry)
            continue
        kept_projects.append(p)

    payload["projects"] = kept_projects
    payload["certifications"] = certs
    payload["achievements"] = achieves
    return payload


def _wrap_string(key: str, text: str) -> dict:
    if key == "projects":
        return {"name": text, "description": None, "technologies": []}
    if key == "experience":
        return {"company": None, "position": text, "duration": None, "description": None}
    return {"institution": text, "degree": None, "field_of_study": None, "graduation_year": None, "grade": None}


def _ground_in_source(payload: dict, source: str) -> dict:
    """Null out fields whose values cannot be verified against the source text.

    This is the line of defense that catches:
      • `https://github.com`  (bare domain the model invented)
      • `"ansharora.cs"`      (LinkedIn handle without the full URL)
      • hallucinated emails that don't appear in the resume
    """
    contact = payload.get("contact") or {}
    src = source.lower()

    # ── LinkedIn ──────────────────────────────────────────────────────────
    # The extracted value must BOTH:
    #   1. Contain "linkedin.com/in/" (i.e. be a full URL, not just a handle)
    #   2. Have the URL actually present in the source text
    # If the resume just says the word "LinkedIn" as hyperlink text with no
    # visible URL, the model should not guess the handle.
    li = contact.get("linkedin")
    if li:
        li_lower = li.lower().strip()
        # Check the extracted value itself looks like a URL
        if "linkedin.com/in/" not in li_lower:
            log.warning(
                "LinkedIn value %r is not a full URL — dropping (resume likely "
                "has hyperlink text without visible URL)", li,
            )
            contact["linkedin"] = None
        # Even if it looks like a URL, verify it's actually in the source text
        elif not re.search(r"linkedin\.com/in/[\w\-_.]+", src):
            log.warning("No LinkedIn URL in source — dropping linkedin=%r", li)
            contact["linkedin"] = None

    # ── GitHub ────────────────────────────────────────────────────────────
    gh = contact.get("github")
    if gh:
        gh_lower = gh.lower().strip().rstrip("/")
        # Bare domain — no real handle
        if gh_lower in {"https://github.com", "http://github.com", "github.com"}:
            log.warning("Dropping bare GitHub domain — no real handle: %r", gh)
            contact["github"] = None
        # Value doesn't look like a GitHub URL at all
        elif "github.com/" not in gh_lower:
            log.warning(
                "GitHub value %r is not a full URL — dropping", gh,
            )
            contact["github"] = None
        # Looks like a URL but not actually in the source
        elif not re.search(r"github\.com/[\w\-_.]+", src):
            log.warning("No GitHub URL in source — dropping github=%r", gh)
            contact["github"] = None

    # ── Email ─────────────────────────────────────────────────────────────
    email = contact.get("email")
    if email and email.lower() not in src:
        log.warning("Email %r not in source — dropping", email)
        contact["email"] = None

    payload["contact"] = contact
    return payload
