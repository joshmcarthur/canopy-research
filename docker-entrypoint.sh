#!/bin/bash
set -e

# Function to handle shutdown
cleanup() {
    echo "Shutting down..."
    kill -TERM "$GUNICORN_PID" 2>/dev/null || true
    kill -TERM "$CADDY_PID" 2>/dev/null || true
    wait "$GUNICORN_PID" 2>/dev/null || true
    wait "$CADDY_PID" 2>/dev/null || true
    exit 0
}

# Trap signals
trap cleanup SIGTERM SIGINT

# Process Caddyfile template with environment variables
echo "Processing Caddyfile template..."

# Set default domain if not provided
if [ -z "$CANOPY_DOMAIN" ]; then
    export CANOPY_DOMAIN=":8080"
    export CANOPY_AUTO_HTTPS="auto_https off"
    echo "No CANOPY_DOMAIN set, using port-based configuration (:8080)"
else
    # When domain is set, auto_https is enabled by default (empty string means use default)
    export CANOPY_AUTO_HTTPS="# auto_https enabled by default"
    echo "Using domain: $CANOPY_DOMAIN (automatic SSL enabled)"
fi

# Generate Caddyfile from template
envsubst < /etc/caddy/Caddyfile.template > /etc/caddy/Caddyfile

# Start Gunicorn in the background
echo "Starting Gunicorn..."
gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    canopyresearch.wsgi:application &
GUNICORN_PID=$!

# Wait a moment for Gunicorn to start
sleep 2

# Check if Gunicorn is still running
if ! kill -0 $GUNICORN_PID 2>/dev/null; then
    echo "Gunicorn failed to start!"
    exit 1
fi

# Start Caddy in the background
echo "Starting Caddy..."
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
CADDY_PID=$!

# Wait for both processes
wait $GUNICORN_PID $CADDY_PID
