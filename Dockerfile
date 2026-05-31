# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS ui
WORKDIR /app/src/quant_lab/terminal/web
COPY src/quant_lab/terminal/web/package.json src/quant_lab/terminal/web/package-lock.json ./
RUN npm ci
COPY src/quant_lab/terminal/web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QUANT_LAB_ROOT=/app \
    TERMINAL_HISTORY_DAYS=14 \
    PORT=8765

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY config ./config
COPY scripts/start_terminal_prod.py ./scripts/start_terminal_prod.py

RUN pip install --no-cache-dir .

COPY --from=ui /app/src/quant_lab/terminal/static/dist ./src/quant_lab/terminal/static/dist

RUN mkdir -p data/raw data/processed

EXPOSE 8765

CMD ["python", "scripts/start_terminal_prod.py"]
