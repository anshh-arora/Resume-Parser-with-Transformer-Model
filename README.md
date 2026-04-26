# Resume Parser with Transformer Model

An LLM-powered resume parser that extracts structured information from PDF and DOCX resumes and outputs clean JSON. Built using Ollama (local or cloud) with a Gradio web UI.

Upload a resume → get back contact info, skills, education, work experience, projects, certifications, and achievements — all neatly formatted as JSON. Optionally, compare the resume against a job description and get a match score with detailed breakdown.

---

## What It Does

- **Reads PDF and DOCX resumes** — drops in a file, extracts the text automatically (including embedded hyperlinks from PDF annotations).
- **Extracts structured data** using a transformer-based LLM (via Ollama):
  - Contact information (name, email, phone, location, LinkedIn, GitHub)
  - Professional summary
  - Skills (deduplicated across all sections)
  - Education history (institution, degree, field, year, grade)
  - Work experience (company, position, duration, description)
  - Projects (name, description, technologies)
  - Certifications and achievements
- **Outputs JSON** — ready to plug into any downstream system.
- **Advanced mode** — paste a job description, get a calibrated match score (skills, experience, education) with strengths, gaps, and a recruiter-style verdict.
- **Anti-hallucination defenses** — small models sometimes invent URLs, fabricate handles, or dump section headers into the wrong fields. The parser catches and corrects these automatically:
  1. **Schema-constrained generation** — the JSON schema is enforced at the model level.
  2. **Sanitization** — garbage entries get filtered out.
  3. **Source grounding** — LinkedIn/GitHub values must be real URLs from the resume text, not guesses.
  4. **Section rescue** — certifications and achievements that the model accidentally puts in "projects" get moved back where they belong.

> **⏱️ A note on speed:** When running a model locally on CPU (e.g. `batiai/gemma4-e2b:q6`), parsing a single resume takes **~30–60 seconds**. This is normal for local inference. To speed things up:
> - Use a **GPU** (even a basic one cuts this to ~5–10 seconds).
> - Use **Ollama Cloud** or any hosted API — response times drop to a few seconds.
> - The match score cache means **re-runs are instant** — the model is only called once per unique resume+JD pair.

---

## Advanced Features (Beyond Basic Requirements)

| Feature | Description |
|---------|-------------|
| **4-Layer Anti-Hallucination Defense** | Schema-constrained generation → Sanitization → Source grounding → Section rescue. Catches fabricated URLs, bare domains, misplaced sections, and garbage entries automatically |
| **PDF Hyperlink Extraction** | Extracts embedded hyperlink URLs from PDF annotation layers — catches LinkedIn/GitHub links that display as clickable text without a visible URL |
| **JD Match Scoring Engine** | Calibrated resume-vs-job-description scoring across skills (50%), experience (35%), and education (15%) with matched/missing skills breakdown and recruiter-style verdict |
| **Score Caching (SHA-256)** | Deterministic on-disk cache keyed by `SHA-256(resume_text + jd_text)` — same inputs return instantly without re-calling the model |
| **Grammar-Constrained Generation** | Pydantic JSON schema passed to Ollama's `format` parameter, forcing valid structured output at the model level |
| **Pre-loaded JD Library** | 4 built-in job descriptions across different roles for instant testing |
| **Docker-Ready Deployment** | Multi-platform Docker setup with compose, volume-mounted score cache, and cross-platform host access |
| **Comprehensive Test Suite** | 23 pytest tests covering extraction, schemas, parsing pipeline, grounding, garbage filtering, rescue logic, and score caching — all run offline |
| **Programmatic API** | Usable as a Python library (`from resume_parser import parse_resume`) without the UI |

---

## Project Structure

```
.
├── app.py                     # Gradio UI (entry point)
├── resume_parser/
│   ├── __init__.py            # Public API exports
│   ├── config.py              # Environment variable loading
│   ├── extractors.py          # PDF / DOCX → plain text (incl. hyperlink extraction)
│   ├── llm.py                 # Ollama client wrapper
│   ├── logging_setup.py       # Coloured timestamped logging
│   ├── parser.py              # Core parsing + anti-hallucination pipeline
│   ├── prompts.py             # System prompts for parsing and scoring
│   ├── schemas.py             # Pydantic models (ParsedResume, MatchScore)
│   └── scoring.py             # JD matching + SHA-256 score cache
├── data/
│   ├── job_descriptions.json  # Pre-loaded JD templates
│   └── score_history.json     # Cached match scores
├── tests/                     # 23 pytest tests (all run offline)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Getting Started (Local — No Docker)

### 1. Set up the environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Start Ollama

You need [Ollama](https://ollama.com/download) running locally with a model pulled:

```bash
ollama serve &                    # start the daemon
ollama pull batiai/gemma4-e2b:q6  # pull the default model (~1.5 GB)
```

Want better accuracy? Use a bigger model:

```bash
ollama pull llama3.1:8b
# then edit .env and set:  OLLAMA_MODEL=llama3.1:8b
```

### 3. Run the app

```bash
python app.py
```

Open **http://127.0.0.1:7860** in your browser. Upload a resume, click **Parse**, wait ~30–60 seconds (local CPU), and you'll see the structured JSON.

### 4. Run tests

```bash
pytest -v
```

All 23 tests run offline (the LLM is mocked) and should pass in under a second.

---

## Getting Started (Docker)

The Docker image talks to an Ollama daemon running on your host machine — it does not bundle Ollama itself, keeping the image small.

### 1. Make sure Ollama is running on your machine

```bash
ollama serve &
ollama pull batiai/gemma4-e2b:q6
```

### 2. Start with docker-compose

```bash
docker compose up --build
```

Open **http://127.0.0.1:7860**. The compose file maps `host.docker.internal:11434` to your host's Ollama daemon automatically.

### 3. Run tests inside the container

```bash
docker compose run --rm resume-parser pytest -v
```

---

## Using Ollama Cloud (Faster)

If you don't want to run models locally, you can use Ollama Cloud with an API key:

**Locally:**
```bash
# Edit .env:
OLLAMA_API_KEY=your_key_from_https_ollama_com
OLLAMA_HOST=https://ollama.com
OLLAMA_MODEL=gpt-oss:120b

python app.py
```

**With Docker:**
```bash
OLLAMA_API_KEY=sk-... \
COMPOSE_OLLAMA_HOST=https://ollama.com \
OLLAMA_MODEL=gpt-oss:120b \
docker compose up
```

---

## How It Works

### Parsing Pipeline

1. **Extract** — `pdfplumber` (for PDFs) or `python-docx` (for DOCX) pulls raw text from the uploaded file. For PDFs, hyperlink URLs are also extracted from the annotation layer (catches LinkedIn/GitHub links that display as clickable text without visible URLs).
2. **Prompt** — the text is sent to the LLM with a system prompt defining the exact JSON schema expected.
3. **Constrain** — the Pydantic schema is passed to Ollama's `format` parameter, forcing the model to generate valid JSON.
4. **Sanitize** — garbage entries (e.g. `certifications_achievements_1_2_3...`) are filtered out.
5. **Rescue** — certifications and achievements that landed in the wrong array get moved to the right place.
6. **Ground** — LinkedIn, GitHub, and email values are verified against the actual resume text. If the resume just says "LinkedIn" as clickable text but doesn't show a URL, the field is set to `null` instead of the model guessing a handle.

### Match Scoring

When you use Advanced mode:
- The parsed resume is scored against the job description across three dimensions: **skills** (50%), **experience** (35%), and **education** (15%).
- The model runs at `temperature=0` for deterministic output.
- Results are cached on disk using a `SHA-256(resume_text + jd_text)` key — same inputs always return the same score instantly.

---

## Configuration

All settings live in `.env`:

| Variable             | Default                    | What it does                                |
| -------------------- | -------------------------- | ------------------------------------------- |
| `OLLAMA_API_KEY`     | _(empty)_                  | Set this for Ollama Cloud. Empty = local.   |
| `OLLAMA_HOST`        | `http://localhost:11434`   | Where to send model requests.               |
| `OLLAMA_MODEL`       | `batiai/gemma4-e2b:q6`     | Model to use (must be pulled on Ollama).    |
| `LOG_LEVEL`          | `INFO`                     | Set to `DEBUG` for verbose extraction logs. |

---

## Tests

```bash
pytest -v    # 23 tests, all pass offline (<1 second)
```

What's covered:
- PDF and DOCX text extraction
- Pydantic schema validation and edge cases
- Full parse pipeline (LLM is mocked)
- Source grounding (LinkedIn handle-only, bare GitHub domain, missing URLs)
- Garbage project filtering (repeating `_N` patterns, section headers)
- Certification/achievement rescue from projects array
- Score caching (same input → cache hit, different input → new call)

---

## Output Format

The parser outputs JSON in this structure:

```json
{
  "contact": {
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "github": "string or null"
  },
  "summary": "string or null",
  "skills": ["string", "..."],
  "education": [
    {
      "institution": "string or null",
      "degree": "string or null",
      "field_of_study": "string or null",
      "graduation_year": "string or null",
      "grade": "string or null"
    }
  ],
  "experience": [
    {
      "company": "string or null",
      "position": "string or null",
      "duration": "string or null",
      "description": "string or null"
    }
  ],
  "projects": [
    {
      "name": "string or null",
      "description": "string or null",
      "technologies": ["string", "..."]
    }
  ],
  "certifications": ["string", "..."],
  "achievements": ["string", "..."]
}
```

---

## Troubleshooting

**"Ollama unreachable" / connection refused**
→ Start the Ollama daemon: `ollama serve &`

**"Model not found"**
→ Pull it: `ollama pull batiai/gemma4-e2b:q6` (or whatever model you configured).

**Docker container can't connect to Ollama**
→ The compose file uses `host.docker.internal:11434`. This works on macOS and Windows automatically. On Linux, the `extra_hosts` block in the compose file handles it.

**Parsing takes over a minute**
→ That's normal for small models on CPU. Use a GPU, a bigger/faster model, or Ollama Cloud for sub-10-second parsing.

**Missing fields in the output**
→ Small models (2B params) lose recall on dense resumes. Switch to `llama3.1:8b` or larger — accuracy improves significantly.

**Legacy .doc files**
→ `python-docx` can't read old binary `.doc` files. Convert to `.docx` or PDF first.

---

## Programmatic Use

You can use the parser as a Python library without the Gradio UI:

```python
from resume_parser import parse_resume, score_against_jd
from resume_parser.extractors import extract_text

# Parse a resume
parsed = parse_resume("path/to/resume.pdf")
print(parsed.contact.name)
print(parsed.skills)

# Score against a job description
resume_text = extract_text("path/to/resume.pdf")
jd = "We need an AI Engineer with LangGraph and Ollama experience…"
score = score_against_jd(parsed, resume_text, jd)
print(f"Overall: {score.overall_score}/100 — {score.verdict}")
```

---

## Author

**Ansh Arora** — AI Engineer

- 📧 [ansharora.cs@gmail.com](mailto:ansharora.cs@gmail.com)
- 💼 [LinkedIn](https://www.linkedin.com/in/ansh-arora-ai-engineer/)
- 🐙 [GitHub](https://github.com/anshh-arora)

---

## License

MIT License — see [LICENSE](./LICENSE) for details.
