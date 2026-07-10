# syntax=docker/dockerfile:1
# ── Elliott Wave Lab — Next.js 15 frontend (Node 20) ──
# Built from apps/web as context (docker-compose sets `context: ./apps/web`).
# Multi-stage: a fat builder compiles the app, a slim runner serves it.

# ---- Stage 1: build ----
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS builder
WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# Install deps from the lockfile first (cached unless package*.json changes).
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time, so the
# API URL the browser will call must be known here. Default = host-mapped backend.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Copy the source and build. `output: "standalone"` (next.config.mjs) emits a
# minimal server + only the deps it traced under .next/standalone.
COPY . .
RUN npm run build

# ---- Stage 2: run ----
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS runner
WORKDIR /app
# NODE_ENV=production tells Next/React to run in prod mode; the standalone
# server reads PORT/HOSTNAME — 0.0.0.0 exposes it outside the container.
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Run as a non-root user (Next.js standalone deployment convention).
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

# Copy ONLY the standalone server and static assets from the build stage — this
# is what keeps the runtime image small (no source, no dev deps, no full modules).
# --chown so the runtime user owns them (standalone writes .next/cache at runtime).
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]

CMD ["node", "server.js"]
