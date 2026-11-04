FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies for Tesseract OCR and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# A non-root runtime user: the API parses untrusted documents, so it must not
# hold privileges it never needs.
RUN adduser --disabled-password --gecos "" --uid 10001 potencia

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=potencia:potencia . .
USER potencia

EXPOSE 8000

# Uses the interpreter rather than curl so the image stays dependency-light.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
