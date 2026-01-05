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
    curl && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy everything
COPY . .

# Install argo-test and its dependencies (which includes kedro-argo)
WORKDIR /app/argo-test
RUN uv sync --frozen

# Install kedro-argo in editable mode into the argo-test venv
# This ensures the plugin entry points are registered
WORKDIR /app/kedro-argo
RUN /app/argo-test/.venv/bin/pip install -e .

ENV PATH=/app/argo-test/.venv/bin:$PATH