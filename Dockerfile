# Multi-stage build for production Django application

# Builder stage
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.11-slim

# Install runtime dependencies and Caddy
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    debian-keyring \
    debian-archive-keyring \
    gnupg \
    gettext-base \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends caddy \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy uv from builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy installed dependencies from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Copy Caddyfile template (will be processed at runtime)
COPY Caddyfile /etc/caddy/Caddyfile.template

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=canopyresearch.settings
# CANOPY_DOMAIN: Set to your domain (e.g., example.com) to enable automatic SSL
# If not set, defaults to :8080 (port-based, no SSL)
ENV CANOPY_DOMAIN=""

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Create directories for Caddy
RUN mkdir -p /var/www/html /etc/caddy /usr/share/caddy /var/lib/caddy \
    && chown -R appuser:appuser /app /var/www/html /etc/caddy /usr/share/caddy /var/lib/caddy

# Make entrypoint and bin scripts executable (they're already copied by COPY . .)
RUN chmod +x /app/docker-entrypoint.sh /app/bin/start

# Switch to non-root user
USER appuser

# Expose ports
# Note: Caddy listens on port 8080 internally (non-root)
# Map to 80/443 externally: docker run -p 80:8080 -p 443:8443
EXPOSE 8080
EXPOSE 8443

# Health check (check Caddy on internal port)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Run entrypoint script (runs migrations/seeds, then executes command or bin/start)
ENTRYPOINT ["/app/docker-entrypoint.sh"]
