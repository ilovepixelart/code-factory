FROM ghcr.io/astral-sh/uv:0.13.9 AS uv
FROM node:26-bookworm-slim AS node
FROM ghcr.io/gitleaks/gitleaks:v8.30.1 AS gitleaks
FROM postgres:18-bookworm

COPY --from=uv /uv /usr/local/bin/uv
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=gitleaks /usr/bin/gitleaks /usr/local/bin/gitleaks
RUN apt-get update && apt-get install -y --no-install-recommends git procps ca-certificates libatomic1 && \
    rm -rf /var/lib/apt/lists/* && \
    node /usr/local/lib/node_modules/npm/bin/npm-cli.js install --global pnpm@12.14.0

ENV UV_CACHE_DIR=/opt/factory-uv \
    UV_PROJECT_ENVIRONMENT=/opt/factory-venv \
    UV_PYTHON_INSTALL_DIR=/opt/factory-python \
    UV_LINK_MODE=copy \
    PNPM_CONFIG_STORE_DIR=/opt/factory-pnpm
WORKDIR /opt/factory-inputs
COPY pyproject.toml uv.lock .python-version ./
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml web/
RUN uv python install && uv sync --locked --no-install-project && \
    uv pip install --python /opt/factory-venv/bin/python uv_build==0.13.9
RUN pnpm --dir web fetch
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap socat ripgrep && \
    rm -rf /var/lib/apt/lists/* && \
    node /usr/local/lib/node_modules/npm/bin/npm-cli.js install --global @anthropic-ai/sandbox-runtime@0.0.83

COPY .code-factory/checks-entrypoint.sh /opt/factory-entrypoint
ENV UV_OFFLINE=1 CODE_FACTORY_OFFLINE=1
ENV PNPM_CONFIG_PACKAGE_IMPORT_METHOD=copy
ENTRYPOINT ["/bin/sh", "/opt/factory-entrypoint"]
