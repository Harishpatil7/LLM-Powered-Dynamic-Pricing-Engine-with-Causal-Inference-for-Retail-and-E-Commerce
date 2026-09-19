# ==============================================================================
# Multi-Stage Production Dockerfile for LLM-DPECI Backend
# ==============================================================================
# Stage 1: Build Stage (Installs compilers, builds wheels, compiles dependencies)
# Stage 2: Runtime Stage (Lightweight, non-root secure execution environment)
# ==============================================================================

# ------------------------------------------------------------------------------
# STAGE 1: BUILDER
# ------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system compilation dependencies required by C-extensions (NumPy, SciPy, EconML)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtual environment for clean layer copying
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only dependency definitions first to leverage Docker layer caching
WORKDIR /build
COPY requirements.txt .

# Install dependencies into virtualenv
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ------------------------------------------------------------------------------
# STAGE 2: RUNTIME
# ------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runner

# Set production runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Install minimal runtime dependencies (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security Best Practice: Create a dedicated non-privileged user and group
# Containers running as root are a major enterprise security vulnerability (CVE surface).
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# Copy virtual environment from builder stage
COPY --from=builder --chown=appuser:appgroup /opt/venv /opt/venv

# Set up application workspace
WORKDIR /app

# Copy application source code and seed data
COPY --chown=appuser:appgroup backend/ ./backend/
COPY --chown=appuser:appgroup data/ ./data/

# Create required runtime directories with appropriate permissions
RUN mkdir -p /app/data/uploads /app/data/artifacts /app/data/processed && \
    chown -R appuser:appgroup /app/data

# Switch to non-root user
USER appuser

# Expose backend API port
EXPOSE 8000

# Define container healthcheck endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start production ASGI server with uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
