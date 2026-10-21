FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV FRONTEND_PATH=/app/frontend
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ ./
COPY --from=frontend /ui/dist ./frontend/
RUN pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home ota \
    && mkdir -p /data/artifacts \
    && chown -R ota:ota /data
USER ota
EXPOSE 8080
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers", "--no-access-log"]
