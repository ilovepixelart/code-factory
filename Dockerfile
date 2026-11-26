FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM node:26-bookworm-slim AS web
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && \
    rm -rf /var/lib/apt/lists/* && npm install --global pnpm@12.14.0
WORKDIR /build
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml web/
RUN pnpm --dir web install --frozen-lockfile
COPY web/ web/
RUN pnpm --dir web build

FROM python:3.14-slim-bookworm AS app
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/factory \
    PATH="/opt/factory/bin:${PATH}"
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src/ src/
COPY --from=web /build/src/code_factory/platform/web/dist/ src/code_factory/platform/web/dist/
RUN uv sync --locked --no-dev --no-editable && \
    useradd --create-home --uid 10001 factory && \
    install -d -o factory -g factory /data /data/state /data/run /data/releases /repositories
COPY scripts/compose-entrypoint.sh /usr/local/bin/code-factory-container
RUN chmod 755 /usr/local/bin/code-factory-container
USER factory
ENTRYPOINT ["code-factory-container"]
CMD ["serve"]
