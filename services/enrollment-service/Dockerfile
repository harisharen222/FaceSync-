# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for compiling cryptography, asyncpg, and OpenCV (headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Install runtime libs needed by OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r nhai && useradd -r -g nhai -d /app -s /sbin/nologin nhai
WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ ./app/

# The models directory is required for the ONNX models.
# In a real environment, an init-container would download these from S3, 
# or they would be baked into the image. We'll create the directory here.
RUN mkdir -p /app/models && chown -R nhai:nhai /app/models

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV=production \
    PORT=8000

USER nhai
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Enrollment handles heavy CPU inference, keep worker count low to avoid thread thrashing
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info", \
     "--access-log"]
