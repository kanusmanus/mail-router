# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Systeempakketten voor PyMuPDF en Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-nld \
    libmupdf-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv installeren
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies eerst (betere layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Applicatiecode
COPY . .

# Logs directory
RUN mkdir -p logs

EXPOSE 8000
