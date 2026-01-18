# KiteCobra Reflex App Dockerfile for Railway
# Single-port deployment using Caddy reverse proxy
FROM python:3.11-slim

# Install Node.js, Caddy, and other dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    git \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y caddy \
    && rm -rf /var/lib/apt/lists/*

# Install bun (used by Reflex for frontend)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY kitecobra ./kitecobra
COPY rxconfig.py .

# Initialize Reflex and export frontend
RUN reflex init

# Export frontend - create production build
RUN reflex export --frontend-only --no-zip && \
    echo "Contents of .web directory:" && \
    ls -la .web/ || echo ".web directory not found"

# Copy exported frontend to Caddy serve directory
# The export creates files directly in .web/_static/
RUN mkdir -p /srv && \
    if [ -d ".web/_static" ]; then \
        cp -r .web/_static/* /srv/ && echo "Copied from .web/_static"; \
    elif [ -d ".web/public" ]; then \
        cp -r .web/public/* /srv/ && echo "Copied from .web/public"; \
    else \
        echo "ERROR: Frontend export directory not found!" && \
        echo "Contents of .web:" && \
        ls -la .web/ && \
        exit 1; \
    fi

# Copy Caddyfile and start script
COPY Caddyfile /etc/caddy/Caddyfile
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Expose single port for Railway
EXPOSE 8080

# Set environment variables
ENV RAILWAY_ENVIRONMENT=production
ENV RAILWAY_PUBLIC_DOMAIN=kitecobra-production.up.railway.app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD ["/app/start.sh"]
