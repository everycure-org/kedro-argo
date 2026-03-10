ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

ENV UV_LINK_MODE=copy

# ---------------------------------
# ------- GPU/System start ------
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    build-essential && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy workspace configuration and both packages
COPY pyproject.toml .
COPY uv.lock .
COPY argo-kedro ./argo-kedro
COPY argo-test/pyproject.toml ./argo-test/

# Sync argo-test from the workspace lockfile
RUN uv sync --frozen --project /app/argo-test --no-install-project

# Copy remaining project files
COPY argo-test ./argo-test

RUN uv sync --frozen --project /app/argo-test

ENV PATH=/app/.venv/bin:$PATH

WORKDIR /app/argo-test