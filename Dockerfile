FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CHROMA_DIR=/app/chroma KB_DIR=/app/kb DB_PATH=/data/triage.db
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY kb ./kb
COPY eval ./eval
COPY tests ./tests
COPY pytest.ini README.md ./

# Download the free embedding model + build the vector index INTO the image,
# so the container never needs to download anything at startup.
RUN mkdir -p /data && python -m scripts.ingest

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
