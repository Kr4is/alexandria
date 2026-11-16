# Use a standard Python image
# Front-end: compile static/src/app.css (Tailwind CLI) into static/dist/app.css
FROM node:26-bookworm-slim AS assets
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY static ./static
COPY templates ./templates
RUN npm run build

FROM python:3.15-slim-bookworm AS builder

# Install uv via pip to avoid GHCR/registry authentication issues
RUN pip install uv

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Final stage
FROM python:3.15-slim-bookworm

WORKDIR /app

# Copy the environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the rest of the application
COPY . .
COPY --from=assets /src/static/dist ./static/dist

# Place executables in the path
ENV PATH="/app/.venv/bin:$PATH"

# Create instance directory
RUN mkdir -p instance

EXPOSE 5000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Runs `flask db upgrade` then starts gunicorn (1 worker = no concurrent SQLite writes)
CMD ["/docker-entrypoint.sh"]
