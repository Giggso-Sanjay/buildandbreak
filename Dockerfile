# Build from repo root (BB): docker build -f buildandbreak/Dockerfile .
# Frontend lives at buildandbreak/frontend/
# Single image: FastAPI backend + React frontend (Orca UI)
# AWS: push to ECR, deploy to ECS/EKS. FE served at /, API at /chat, /health.

# ─── Stage 1: Build frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Install deps
COPY buildandbreak/frontend/package*.json ./
RUN npm ci

# Build with empty API base (same-origin in prod)
COPY buildandbreak/frontend/ ./
ENV VITE_API_BASE_URL=
RUN npm run build

# ─── Stage 2: Python backend + serve frontend ────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Backend deps
COPY buildandbreak/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY buildandbreak/ ./

# Frontend static files from stage 1
COPY --from=frontend-builder /app/dist ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
