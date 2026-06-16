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
COPY scripts/ ./scripts/
COPY spec.yaml ./spec.yaml

# Create a seed workspace. docker-compose may later mount ./workspaces over this
# path, so the entrypoint also repairs the runtime workspace on startup.
RUN mkdir -p /app/workspaces/default/data \
    && cp /app/spec.yaml /app/workspaces/default/spec.yaml

ENV PYTHONPATH=/app/src:/app
ENV DEFAULT_WORKSPACE=/app/workspaces/default
ENV AGENTOS_USER_DATA_ROOT=/var/lib/agentos/user
ENV LOG_LEVEL=WARNING

# Default container command serves the Docker-first runtime preview.
# CLI prompt runs remain available through docker-compose service overrides.
ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8787"]
