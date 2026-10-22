FROM ghcr.io/astral-sh/uv:0.11.26 AS installer
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates mariadb-client build-essential pkg-config libmariadb-dev libffi-dev yarn libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 chromium fontconfig fonts-liberation fonts-dejavu-core fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji && rm -rf /var/lib/apt/lists/*
RUN chromium --version && fc-match sans
COPY --from=installer /uv /uvx /usr/local/bin/
WORKDIR /app
COPY review/prepare-deps review/prepare-build review/
COPY package.json yarn.lock ./
COPY scripts/socket scripts/socket/
COPY frontend/package.json frontend/
COPY roster/package.json roster/
RUN ./review/prepare-deps
RUN apt-get update && apt-get install -y --no-install-recommends fonts-inter && rm -rf /var/lib/apt/lists/*
COPY . .
RUN .venv/bin/python docker/bundle-fonts.py
RUN ./review/prepare-build
ENV PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin" FRAPPE_PRELOAD_DATABASE_DRIVERS=none
CMD ["./docker/serve"]
