# --- Stage 1: Build React Frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# --- Stage 2: Build Production Server ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Setup Backend
WORKDIR /app/backend
COPY backend/requirements.txt .
# Playwright's Python package doesn't include the browser: install Chromium
# and its system libraries, or every scrape fails at launch.
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY backend/ .

# Copy pre-built frontend from stage 1 into correct path relative to backend
WORKDIR /app/frontend
COPY --from=frontend-builder /app/frontend/dist ./dist

# Expose final port
EXPOSE 8000
WORKDIR /app/backend

# Startup command. One worker: each worker process runs its own Chromium,
# cache and 8-request concurrency budget, so extra workers multiply memory
# use and the request bursts GeM's WAF blocks.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
