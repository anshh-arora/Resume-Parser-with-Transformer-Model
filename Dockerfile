FROM python:3.13-slim

WORKDIR /app

# System packages required by pdfplumber (Pillow image backends + libstdc++).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY resume_parser ./resume_parser
COPY tests ./tests
COPY data ./data
COPY app.py ./

ENV PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    OLLAMA_MODEL=batiai/gemma4-e2b:q6 \
    LOG_LEVEL=INFO

EXPOSE 7860

CMD ["python", "app.py"]
