ARG IMAGE=nvidia/cuda:13.1.1-base-ubuntu24.04

# --- Build stage: install dependencies only (cached) ---
FROM $IMAGE AS deps

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_INSTALL_DIR=/app/python \
    DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --frozen --no-install-project

# --- Runtime stage ---
FROM $IMAGE

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

# Copy pre-built Python + venv in one layer (cached unless pyproject.toml/uv.lock change)
COPY --from=deps /app /app
ENV PATH=/app/.venv/bin:$PATH
ENV UV_PYTHON_INSTALL_DIR=/app/python

# Copy source and install only the project package (tiny layer)
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps --no-compile --python /app/.venv/bin/python .