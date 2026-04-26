"""Gradio interface for the resume parser.

Two modes:
  • Normal — upload a resume, get structured JSON.
  • Advanced — also paste a job description and get a calibrated match score.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import traceback
from pathlib import Path

import gradio as gr

from resume_parser import list_jds, parse_resume, score_against_jd
from resume_parser.config import OLLAMA_API_KEY, OLLAMA_HOST, OLLAMA_MODEL
from resume_parser.extractors import extract_text
from resume_parser.llm import health_check
from resume_parser.logging_setup import get_logger, setup_logging

setup_logging()
log = get_logger("app")

DEFAULT_JD_TITLE = "Junior AI Engineer — Agentic Systems"

CSS = """
#header { text-align: center; padding: 8px 0 4px; }
#header h1 { margin: 0; font-size: 28px; letter-spacing: -0.5px; }
#header p { margin: 4px 0 0; color: #6b7280; }
.gradio-container { max-width: 1200px !important; margin: 0 auto !important; }
footer { display: none !important; }
.score-card {
  border: 1px solid #e5e7eb; border-radius: 14px; padding: 18px 22px;
  background: linear-gradient(180deg, #fafafa 0%, #ffffff 100%);
}
.score-card .big {
  font-size: 56px; font-weight: 700; line-height: 1;
  background: linear-gradient(135deg, #6366f1, #06b6d4);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.bar { height: 8px; background: #eef2f7; border-radius: 999px; overflow: hidden; margin-top: 6px; }
.bar > div { height: 100%; background: linear-gradient(90deg, #6366f1, #06b6d4); }
.kv { display: flex; justify-content: space-between; margin: 6px 0; font-size: 14px; }
.kv b { color: #111827; }
.banner { padding: 10px 14px; border-radius: 10px; margin-bottom: 12px; font-size: 14px; }
.banner.ok   { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
.banner.warn { background: #fffbeb; color: #92400e; border: 1px solid #fcd34d; }
"""


def _save_temp(file_obj) -> Path:
    """Gradio passes a NamedString / dict / path; copy to a stable temp path."""
    src = Path(file_obj.name if hasattr(file_obj, "name") else file_obj)
    dst = Path(tempfile.mkdtemp()) / src.name
    shutil.copy(src, dst)
    log.info("Saved upload → %s (%d bytes)", dst, dst.stat().st_size)
    return dst


def _bar(label: str, value: int) -> str:
    return (
        f'<div class="kv"><span>{label}</span><b>{value}/100</b></div>'
        f'<div class="bar"><div style="width:{value}%"></div></div>'
    )


def _score_card(score) -> str:
    return f"""
<div class="score-card">
  <div style="display:flex; align-items:baseline; gap:14px;">
    <div class="big">{score.overall_score}</div>
    <div style="color:#6b7280;">Overall match</div>
  </div>
  <div style="margin-top:14px;">
    {_bar("Skills", score.skills_match)}
    {_bar("Experience", score.experience_match)}
    {_bar("Education", score.education_match)}
  </div>
  <p style="margin-top:14px; color:#374151;"><b>Verdict:</b> {score.verdict}</p>
</div>
"""


def _format_error(exc: Exception) -> str:
    """Return a user-friendly hint and log the full traceback to terminal."""
    log.error("Request failed:\n%s", traceback.format_exc())
    name = type(exc).__name__
    msg = str(exc) or name
    if "Connection" in name or "Connection" in msg or "refused" in msg.lower():
        hint = (
            "Cannot reach the Ollama server. "
            "Either set OLLAMA_API_KEY in .env (cloud) or start a local daemon "
            "with `ollama serve` and ensure the model is pulled (`ollama pull <model>`)."
        )
        return f"⚠️ {hint}\n\nDetails: {name}: {msg}"
    if "model" in msg.lower() and ("not found" in msg.lower() or "404" in msg):
        return (
            f"⚠️ Model '{OLLAMA_MODEL}' not available at {OLLAMA_HOST}. "
            f"Pull it locally (`ollama pull {OLLAMA_MODEL}`) or change OLLAMA_MODEL in .env."
            f"\n\nDetails: {name}: {msg}"
        )
    return f"⚠️ {name}: {msg}"


def run_normal(file, progress=gr.Progress()):
    if file is None:
        return "Upload a resume to begin.", None
    log.info("== Normal mode request ==")
    try:
        progress(0.1, desc="📎 Reading file…")
        path = _save_temp(file)
        progress(0.2, desc="📄 Extracting text from resume…")
        progress(0.3, desc="🤖 Sending to model (this takes ~30-60s on a local CPU)…")
        parsed = parse_resume(path)
        progress(0.9, desc="✅ Done! Formatting output…")
        payload = parsed.model_dump()
        log.info("== Normal mode OK ==")
        return json.dumps(payload, indent=2, ensure_ascii=False), payload
    except Exception as exc:
        return _format_error(exc), None


def run_advanced(file, jd_text, progress=gr.Progress()):
    if file is None:
        return "Upload a resume.", None, "", "", ""
    if not jd_text or not jd_text.strip():
        return "Paste or pick a job description.", None, "", "", ""
    log.info("== Advanced mode request (JD chars=%d) ==", len(jd_text))
    try:
        progress(0.05, desc="📎 Reading file…")
        path = _save_temp(file)
        progress(0.10, desc="📄 Extracting text from resume…")
        resume_text = extract_text(path)
        progress(0.20, desc="🤖 Parsing resume with model (this takes ~30-60s on local CPU)…")
        parsed = parse_resume(path)
        progress(0.60, desc="📊 Scoring against job description…")
        score = score_against_jd(parsed, resume_text, jd_text)

        progress(0.90, desc="✅ Done! Formatting output…")
        matched = "\n".join(f"• {s}" for s in score.matched_skills) or "—"
        missing = "\n".join(f"• {s}" for s in score.missing_skills) or "—"
        strengths = "\n".join(f"• {s}" for s in score.strengths) or "—"
        gaps = "\n".join(f"• {s}" for s in score.gaps) or "—"
        details = (
            f"### Strengths\n{strengths}\n\n"
            f"### Gaps\n{gaps}\n\n"
            f"### Matched skills\n{matched}\n\n"
            f"### Missing skills\n{missing}"
        )
        log.info("== Advanced mode OK (overall=%d) ==", score.overall_score)
        return (
            json.dumps(parsed.model_dump(), indent=2, ensure_ascii=False),
            parsed.model_dump(),
            _score_card(score),
            details,
            json.dumps(score.model_dump(), indent=2, ensure_ascii=False),
        )
    except Exception as exc:
        return _format_error(exc), None, "", "", ""


def load_jd_template(title: str) -> str:
    return list_jds().get(title, "")


def _startup_banner() -> str:
    ok, message = health_check()
    if ok:
        return f'<div class="banner ok">✓ {message} · model <code>{OLLAMA_MODEL}</code></div>'
    hint = (
        "Set <code>OLLAMA_API_KEY</code> in <code>.env</code> for Ollama Cloud, "
        "or start a local daemon with <code>ollama serve</code>."
    )
    log.warning(message)
    return f'<div class="banner warn">⚠ {message}<br><small>{hint}</small></div>'


APP_BUILD = "v2-anti-hallucination"  # bump whenever parser logic changes


def _print_startup() -> None:
    log.info("=" * 60)
    log.info("Resume Parser starting up  [build=%s]", APP_BUILD)
    log.info("  host  : %s", OLLAMA_HOST)
    log.info("  model : %s", OLLAMA_MODEL)
    log.info("  cloud : %s", "yes" if OLLAMA_API_KEY else "no (local daemon expected)")
    log.info("  defenses: schema-constrained generation + source grounding + garbage filter")
    log.info("=" * 60)


def build_app() -> gr.Blocks:
    _print_startup()
    jd_library = list_jds()
    jd_titles = list(jd_library.keys())
    default_jd = jd_library.get(DEFAULT_JD_TITLE, "")
    banner_html = _startup_banner()

    with gr.Blocks(title="Resume Parser") as app:
        gr.HTML(
            '<div id="header"><h1>📄 Resume Parser</h1>'
            '<p>Transformer-powered extraction with optional JD scoring · '
            f'<code>{OLLAMA_MODEL}</code> via <code>{OLLAMA_HOST}</code> · '
            f'build <code>{APP_BUILD}</code></p></div>'
        )
        gr.HTML(banner_html)

        with gr.Tabs():
            with gr.Tab("Normal"):
                gr.Markdown(
                    "Upload a resume (PDF / DOCX). The model returns structured JSON "
                    "covering contact info, skills, education, experience, projects, and more.\n\n"
                    "⏱️ **Note:** On a local CPU model, parsing takes ~30-60 seconds. "
                    "Using an API-hosted model or a GPU server is significantly faster."
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        n_file = gr.File(label="Resume", file_types=[".pdf", ".docx", ".doc"])
                        n_btn = gr.Button("Parse", variant="primary")
                    with gr.Column(scale=2):
                        n_json = gr.Code(label="JSON output", language="json", lines=22)
                        n_obj = gr.JSON(label="Structured view", visible=False)
                n_btn.click(run_normal, inputs=n_file, outputs=[n_json, n_obj])

            with gr.Tab("Advanced — JD Match"):
                gr.Markdown(
                    "Pick a pre-filled JD or paste your own. The model returns parsed JSON "
                    "**plus** a calibrated match score. Scores are cached on disk, so re-running "
                    "the same resume + JD returns the same numbers instantly."
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        a_file = gr.File(label="Resume", file_types=[".pdf", ".docx", ".doc"])
                        a_template = gr.Dropdown(
                            choices=jd_titles,
                            value=DEFAULT_JD_TITLE if DEFAULT_JD_TITLE in jd_titles else (jd_titles[0] if jd_titles else None),
                            label="JD template",
                        )
                        a_jd = gr.Textbox(
                            label="Job description",
                            value=default_jd,
                            lines=14,
                            placeholder="Paste the JD here…",
                        )
                        a_btn = gr.Button("Parse & Score", variant="primary")
                    with gr.Column(scale=2):
                        a_card = gr.HTML()
                        a_details = gr.Markdown()
                        with gr.Accordion("Parsed resume JSON", open=False):
                            a_json = gr.Code(language="json", lines=20)
                        with gr.Accordion("Raw score JSON", open=False):
                            a_score_json = gr.Code(language="json", lines=14)
                        a_obj = gr.JSON(visible=False)

                a_template.change(load_jd_template, inputs=a_template, outputs=a_jd)
                a_btn.click(
                    run_advanced,
                    inputs=[a_file, a_jd],
                    outputs=[a_json, a_obj, a_card, a_details, a_score_json],
                )

    return app


if __name__ == "__main__":
    import os
    build_app().launch(
        css=CSS,
        theme=gr.themes.Soft(primary_hue="indigo"),
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
