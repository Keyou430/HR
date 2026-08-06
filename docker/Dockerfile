# HR Platform — Production Dockerfile (multi-stage)
# Build:  docker build -t hr-platform -f docker/Dockerfile .
# Run:    docker compose -f docker/compose.yml up -d

# Stage 1: Build frontend
FROM node:25-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app

# Create non-root user
RUN groupadd -r hr && useradd -r -g hr hr

# Install system dependencies (curl for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy frontend dist (served via named volume to nginx)
COPY --from=frontend-builder /frontend/dist /app/static

# Copy utility scripts
COPY docker/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# Create data directory for backups
RUN mkdir -p /app/data/backups && chown -R hr:hr /app

USER hr

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
