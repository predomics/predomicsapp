# =============================================================================
# Stage 1: Build Vue.js frontend
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2: Build gpredomicspy (Rust → Python native module)
# =============================================================================
FROM python:3.11-slim AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git pkg-config libssl-dev && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.84.0 && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir maturin

ARG GPREDOMICS_REF=main
ARG GPREDOMICSPY_REF=main

WORKDIR /build
RUN git clone --depth 1 --branch ${GPREDOMICS_REF} https://github.com/predomics/gpredomics.git && \
    git clone --depth 1 --branch ${GPREDOMICSPY_REF} https://github.com/predomics/gpredomicspy.git
RUN cd gpredomicspy && maturin build --release --out /build/wheels

# =============================================================================
# Stage 3: Runtime — Python backend + frontend + gpredomicspy wheel
# =============================================================================
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="PredomicsApp" \
      org.opencontainers.image.description="Web application for gpredomics — sparse interpretable ML model discovery" \
      org.opencontainers.image.source="https://github.com/predomics/predomicsapp" \
      org.opencontainers.image.licenses="GPL-3.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install gpredomicspy wheel (built in stage 2)
COPY --from=rust-builder /build/wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Install Python backend dependencies (locked versions)
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && rm /tmp/requirements.lock

# Copy backend code
COPY backend/ backend/

# Copy built frontend into static directory
COPY --from=frontend-builder /app/frontend/dist backend/app/static/

# Copy bundled demo datasets (read-only, baked in image)
COPY samples/ samples/

# Create directories for user workspace (persistent volume mount point)
RUN mkdir -p data/uploads data/projects data/datasets

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
