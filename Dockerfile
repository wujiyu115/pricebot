# ---- frontend build ----
FROM oven/bun:1 AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# ---- runtime ----
FROM python:3.12-slim
WORKDIR /app

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=6106

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY app/ ./app/
COPY config/default_settings.json ./config/default_settings.json
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN mkdir -p data logs

EXPOSE 6106

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6106/api/dashboard', timeout=4)" || exit 1

CMD ["python", "main.py"]
