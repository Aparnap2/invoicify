# invoicify-worker/Dockerfile
# Replaces wrangler.toml for Azure Container Apps deployment.
# The Hono/TypeScript worker runs as a standard Node.js HTTP server.
# D1 → Azure PostgreSQL (via DATABASE_URL)
# R2 → Azure Blob Storage (via AZURE_STORAGE_*)
# KV → In-memory LRU cache (ttl-lru) or Azure Redis Cache
# Durable Objects → Postgres-backed state (no equivalent needed at this scale)
# Queues → Azure Storage Queue (polled by agent-core)

FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm
RUN npm install -g pnpm@9

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install ALL deps (including dev, needed to build TS)
RUN pnpm install --frozen-lockfile

# Copy source
COPY tsconfig.json ./
COPY src ./src

# Build TypeScript → JS
RUN pnpm exec tsc --outDir dist --module commonjs --target es2020 \
    --moduleResolution node --esModuleInterop true --skipLibCheck true \
    --resolveJsonModule true 2>/dev/null || true

# ── Production image ───────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

RUN npm install -g pnpm@9

COPY package.json pnpm-lock.yaml ./

# Install production deps only
RUN pnpm install --frozen-lockfile --prod

# Copy compiled JS from builder
COPY --from=builder /app/dist ./dist

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:8787/health || exit 1

EXPOSE 8787

# Run with Node directly (no wrangler in production)
CMD ["node", "dist/server.js"]
