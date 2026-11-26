# syntax=docker/dockerfile:1.7
#
# PredomicsApp image.
#
#   docker build -t predomicsapp .                 # production image (last stage)
#   docker build --target dev -t predomicsapp:dev . # + test tooling (pytest, ruff)
#
# Needs BuildKit (default since Docker 23). The first build compiles the Rust
# engine and takes 10-25 minutes; later builds reuse the cache mounts below.

# ---------------------------------------------------------------------------
# Build inputs (override with --build-arg / compose build.args)
# ---------------------------------------------------------------------------
# Base images are pinned by digest (tag kept for readability). Dependabot opens a
# pull request when a tag moves to a new digest; CI then rebuilds and tests.

# Engine pin. Exact commits of predomics/gpredomics and predomics/gpredomicspy
# that this version of the app was built and tested against. Any git ref works
# (commit, tag or branch), but only a commit or tag gives a reproducible image.
# TODO: replace by release tags once both repositories are tagged.
ARG GPREDOMICS_REF=faff348892ca0047de560daf41ec89029861b4fe
ARG GPREDOMICSPY_REF=d963ec310be71afc7f9517084d6a348450160029

# =============================================================================
# Stage 1: Build Vue.js frontend
# =============================================================================
FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2: Build gpredomicspy (Rust → Python native module)
# =============================================================================
FROM python:3.11-slim@sha256:61e01f72680f86a5279ad510818ab7b2ee9f049822589d4e34e33e044360356c AS rust-builder

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CARGO_NET_RETRY=10 \
    CARGO_HTTP_TIMEOUT=300

# System packages and the Rust toolchain are separate layers, so a failed
# toolchain download does not redo the apt step.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl git pkg-config libssl-dev && \
    rm -rf /var/lib/apt/lists/*

ARG RUST_TOOLCHAIN=1.88.0
RUN curl --proto '=https' --tlsv1.2 --retry 8 --retry-delay 5 --retry-all-errors -sSf \
      https://sh.rustup.rs -o /tmp/rustup-init.sh && \
    sh /tmp/rustup-init.sh -y --profile minimal --default-toolchain "${RUST_TOOLCHAIN}" && \
    rm /tmp/rustup-init.sh
ENV PATH="/root/.cargo/bin:${PATH}"

ARG MATURIN_VERSION=1.16.0
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "maturin==${MATURIN_VERSION}"

ARG GPREDOMICS_REF
ARG GPREDOMICSPY_REF
# Only useful when a *_REF is a moving branch: change the value to force a re-fetch.
ARG CACHEBUST=0

WORKDIR /build
# Fetch exactly the requested ref (commit, tag or branch) of each repository and
# record the commit that was actually built.
RUN set -eux; \
    echo "cache bust: ${CACHEBUST}"; \
    fetch() { \
        git init -q "$1"; \
        git -C "$1" remote add origin "https://github.com/predomics/$1.git"; \
        n=0; until git -C "$1" fetch -q --depth 1 origin "$2"; do \
            n=$((n+1)); [ "$n" -lt 5 ] || exit 1; sleep 5; \
        done; \
        git -C "$1" checkout -q FETCH_HEAD; \
        git -C "$1" rev-parse HEAD > "/build/$1.sha"; \
    }; \
    fetch gpredomics "${GPREDOMICS_REF}"; \
    fetch gpredomicspy "${GPREDOMICSPY_REF}"; \
    cat /build/gpredomics.sha /build/gpredomicspy.sha

# gpredomicspy depends on ../gpredomics by path. Its Cargo.lock is not committed
# upstream, so `--locked` cannot be used yet (crates.io versions are resolved at
# build time; see DEPLOYMENT.md "Reproducibility").
WORKDIR /build/gpredomicspy
RUN --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    --mount=type=cache,target=/build/gpredomicspy/target \
    maturin build --release --out /build/wheels

# =============================================================================
# Stage 3: Runtime — Python backend + frontend + gpredomicspy wheel
# =============================================================================
FROM python:3.11-slim@sha256:61e01f72680f86a5279ad510818ab7b2ee9f049822589d4e34e33e044360356c AS runtime

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    # The app runs as an unprivileged user: keep caches out of site-packages.
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    MPLCONFIGDIR=/tmp/matplotlib \
    XDG_CACHE_HOME=/tmp/.cache

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --no-log-init --home-dir /home/app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# 1. Locked Python dependencies first (the big, rarely changing layer). Every
#    file is checked against the SHA-256 recorded in the lock.
COPY backend/requirements.lock /tmp/requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes -r /tmp/requirements.lock && rm /tmp/requirements.lock

# 2. The engine wheel on top, without letting it pull unpinned dependencies.
RUN --mount=type=bind,from=rust-builder,source=/build/wheels,target=/tmp/wheels \
    --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps /tmp/wheels/*.whl

# Copy backend code
COPY backend/ backend/

# Copy built frontend into static directory
COPY --from=frontend-builder /app/frontend/dist backend/app/static/

# Copy bundled demo datasets (read-only, baked in image)
COPY samples/ samples/

# Record which engine commits are inside this image.
COPY --from=rust-builder /build/gpredomics.sha /build/gpredomicspy.sha /app/engine/

COPY --chmod=0755 scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# User workspace (persistent volume mount point), owned by the app user.
RUN mkdir -p data/uploads data/projects data/datasets && \
    chown -R app:app /app/data && \
    python -m compileall -q backend

# APP_VERSION: set by the release workflow from the git tag. Empty = the app
# reports the version of backend/pyproject.toml.
ARG APP_VERSION=""
ARG VCS_REF=unknown
ARG GPREDOMICS_REF
ARG GPREDOMICSPY_REF

# Reported by GET /health (version, engine_ref, enginepy_ref).
ENV PREDOMICS_VERSION=${APP_VERSION} \
    PREDOMICS_ENGINE_REF=${GPREDOMICS_REF} \
    PREDOMICS_ENGINEPY_REF=${GPREDOMICSPY_REF}

# Licence label kept as it was; the project licence is still to be confirmed by
# the owners (no LICENSE file yet, see README "Licence").
LABEL org.opencontainers.image.title="PredomicsApp" \
      org.opencontainers.image.description="Web application for gpredomics — sparse interpretable ML model discovery" \
      org.opencontainers.image.source="https://github.com/predomics/predomicsapp" \
      org.opencontainers.image.licenses="GPL-3.0" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      io.predomics.gpredomics.ref="${GPREDOMICS_REF}" \
      io.predomics.gpredomicspy.ref="${GPREDOMICSPY_REF}"

EXPOSE 8000

# /health/ready also checks the database and the data volume (HTTP 503 if not usable).
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=8)" || exit 1

# The entrypoint starts as root only to fix the ownership of the data volume
# (volumes created by older, root-running images), then drops to the `app` user
# (uid 10001). Started with an explicit non-root user (e.g. Kubernetes
# runAsUser) it runs the command directly.
ENTRYPOINT ["docker-entrypoint.sh"]

# FORWARDED_ALLOW_IPS (env) lists the proxies whose X-Forwarded-* headers are
# trusted; the default (127.0.0.1) is right when the port is published directly.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

# =============================================================================
# Stage 4 (optional): development / test image — `docker build --target dev`
# =============================================================================
FROM runtime AS dev

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "pytest>=8,<10" "pytest-asyncio>=0.23" "pytest-cov>=5" "aiosqlite>=0.19" "ruff>=0.6" "pip-audit>=2.7"

# =============================================================================
# Default target: the production runtime image
# =============================================================================
FROM runtime AS production
