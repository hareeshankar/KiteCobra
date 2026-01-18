# KiteCobra Reflex App Dockerfile for Railway
FROM python:3.11-slim

# Install Node.js and bun
RUN apt-get update && apt-get install -y curl unzip && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    curl -fsSL https://bun.sh/install | bash && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.bun/bin:${PATH}"

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY kitecobra ./kitecobra
COPY rxconfig.py .

# Initialize Reflex
RUN reflex init

# Set environment
ENV RAILWAY_ENVIRONMENT=production
ENV RAILWAY_PUBLIC_DOMAIN=kitecobra-production.up.railway.app
ENV PYTHONUNBUFFERED=1

# Run on port 8080
EXPOSE 8080
CMD reflex run --env prod --loglevel debug --backend-host 0.0.0.0 --backend-port 8080
