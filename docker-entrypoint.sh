#!/bin/bash
set -e

# Database setup: Run migrations
if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput
    echo "Migrations completed."
else
    echo "Skipping migrations (SKIP_MIGRATIONS=true)"
fi

# Optional: Run seed command (skip by default)
if [ "${SKIP_SEEDS:-true}" != "true" ]; then
    echo "Running seed command..."
    python manage.py seed
    echo "Seed command completed."
else
    echo "Skipping seeds (SKIP_SEEDS=true or not set)"
fi

# If no command provided, default to production server
if [ $# -eq 0 ]; then
    exec /app/bin/start
fi

# Execute the provided command
exec "$@"
