# ── Frontend production image (Next.js standalone) ──────────────
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies (no lockfile committed yet → use install, not ci)
COPY package.json ./
RUN npm install

# Copy source and build.
COPY . .

# NEXT_PUBLIC_* are compiled into the client bundle at build time.
# Provided via docker-compose build args.
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_MAX_RANGE_DAYS=92
ARG NEXT_PUBLIC_JOB_POLL_INTERVAL_MS=3000
ARG NEXT_PUBLIC_ENABLE_ASSISTANT=false
ARG NEXT_PUBLIC_IDLE_TIMEOUT_MIN=15
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_MAX_RANGE_DAYS=${NEXT_PUBLIC_MAX_RANGE_DAYS} \
    NEXT_PUBLIC_JOB_POLL_INTERVAL_MS=${NEXT_PUBLIC_JOB_POLL_INTERVAL_MS} \
    NEXT_PUBLIC_ENABLE_ASSISTANT=${NEXT_PUBLIC_ENABLE_ASSISTANT} \
    NEXT_PUBLIC_IDLE_TIMEOUT_MIN=${NEXT_PUBLIC_IDLE_TIMEOUT_MIN}

RUN npm run build

# ── Runtime stage ───────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Copy the standalone server + static assets.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
