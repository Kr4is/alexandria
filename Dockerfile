# Use a standard Python image
FROM python:3.13-slim-bookworm AS builder

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
FROM python:3.13-slim-bookworm

WORKDIR /app

# Copy the environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the rest of the application
COPY . .

# Place executables in the path
ENV PATH="/app/.venv/bin:$PATH"

# Create instance directory
RUN mkdir -p instance

EXPOSE 5000

CMD ["python", "app.py"]
