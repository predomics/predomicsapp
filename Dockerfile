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
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir maturin

WORKDIR /build
COPY gpredomicspy/ ./gpredomicspy/
RUN cd gpredomicspy && maturin build --release --out /build/wheels

# =============================================================================
# Stage 3: Runtime — Python backend + frontend + gpredomicspy wheel
# =============================================================================
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install gpredomicspy wheel (built in stage 2)
COPY --from=rust-builder /build/wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Install Python backend dependencies
COPY backend/pyproject.toml backend/
RUN pip install --no-cache-dir backend/

# Copy backend code
COPY backend/ backend/

# Copy built frontend into static directory
COPY --from=frontend-builder /app/frontend/dist backend/static/

# Copy sample data
COPY data/qin2014_cirrhosis/ data/qin2014_cirrhosis/

# Create directories for runtime data
RUN mkdir -p data/uploads data/projects

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
