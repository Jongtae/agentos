# AgentOS — Docker image
# Base: python:3.12-slim (Debian bookworm)
# Playwright is NOT included in this image (Phase 3: separate Dockerfile.browser)

FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY workspaces/ ./workspaces/

# Create data directory
RUN mkdir -p /app/workspaces/default/data

ENV PYTHONPATH=/app/src
ENV DEFAULT_WORKSPACE=/app/workspaces/default
ENV LOG_LEVEL=WARNING

# TUI requires a real terminal — run with: docker compose run --rm agent-os
ENTRYPOINT ["python", "src/main.py"]
