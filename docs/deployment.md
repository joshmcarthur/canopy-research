# Deployment Guide

## Docker Image Architecture

This application uses **Caddy + Gunicorn** architecture:

- **Caddy**: Handles SSL/TLS certificates, serves static files, and reverse proxies to Gunicorn
- **Gunicorn**: Runs Django WSGI application

## Running the Docker Image

### Basic Usage (Development/Testing)

```bash
# Build the image
docker build -t canopy-research .

# Run with port mapping (maps internal 8080 to external 80)
# No domain needed - uses port-based configuration
docker run -p 80:8080 canopy-research
```

### Production with Domain (Automatic SSL)

When deploying with a domain name, simply set the `CANOPY_DOMAIN` environment variable. No need to rebuild the image!

```bash
# Run with domain (automatic SSL enabled)
docker run -p 80:8080 -p 443:8443 \
  -e CANOPY_DOMAIN=example.com \
  -e ALLOWED_HOSTS=example.com \
  canopy-research
```

**What happens:**

- Caddy automatically provisions Let's Encrypt SSL certificates
- Certificates are automatically renewed
- HTTP is automatically redirected to HTTPS
- Django's `ALLOWED_HOSTS` is automatically configured from `CANOPY_DOMAIN`

**Note:** If you set `ALLOWED_HOSTS` explicitly, it takes precedence over the auto-configured value from `CANOPY_DOMAIN`.

### Port Mapping

The container exposes:

- Port `8080` (HTTP) - map to `80` externally
- Port `8443` (HTTPS) - map to `443` externally (when using domain)

Example Docker run:

```bash
docker run -p 80:8080 -p 443:8443 canopy-research
```

### Behind Another Reverse Proxy

Yes, you can put another reverse proxy (like Nginx, Caddy, or a load balancer) in front of this container. The external proxy would:

1. Handle SSL termination (if desired)
2. Forward requests to the container on port 8080
3. Optionally handle load balancing across multiple container instances

Example with Docker Compose and external Caddy:

```yaml
services:
  app:
    image: ghcr.io/joshmcarthur/canopy-research:latest
    ports:
      - "127.0.0.1:8080:8080" # Only expose to localhost

  caddy:
    image: caddy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile-external:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
```

## Environment Variables

### Domain Configuration

- `CANOPY_DOMAIN`: Domain name for the application (e.g., `example.com`)
  - If set: Enables automatic SSL with Let's Encrypt
  - If not set: Uses port-based configuration (`:8080`) without SSL
  - Example: `-e CANOPY_DOMAIN=example.com`

### Django Configuration

- `DJANGO_SETTINGS_MODULE`: Set to `canopyresearch.settings` (default)
- `DEBUG`: Enable debug mode (default: `False`)
  - Set to `true` to enable debug mode: `-e DEBUG=true`
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
  - Example: `-e ALLOWED_HOSTS=example.com,www.example.com`
  - If not set and `CANOPY_DOMAIN` is provided, automatically uses `CANOPY_DOMAIN`
- `PYTHONUNBUFFERED`: Set to `1` for proper logging (default)

### Example with All Options

```bash
docker run -p 80:80 -p 443:443 \
  -e CANOPY_DOMAIN=example.com \
  -e ALLOWED_HOSTS=example.com,www.example.com \
  -e DEBUG=false \
  canopy-research
```

## Health Checks

The container includes a health check that verifies Caddy is responding on port 8080.

## Static Files

Static files are collected during the Docker build process and served directly by Caddy from `/app/staticfiles`. This is more efficient than serving them through Django.

## Media Files

If you need to serve user-uploaded media files, uncomment the media handler in the Caddyfile and ensure the media directory is mounted as a volume in production.
