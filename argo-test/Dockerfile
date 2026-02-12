ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

ENV UV_LINK_MODE=copy
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

ENV UV_LINK_MODE=copy
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --frozen --no-install-project
ENV PATH=/app/.venv/bin:$PATH

COPY . .

RUN uv sync --frozen