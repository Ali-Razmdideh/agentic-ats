# syntax=docker/dockerfile:1.6
# Two-stage Next.js build. Standalone output keeps the runtime image small.
ARG NODE_VERSION=20

# ---------- builder ----------
FROM node:${NODE_VERSION}-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY tsconfig.json next.config.mjs tailwind.config.ts postcss.config.mjs ./
COPY src ./src

RUN npm run build

# ---------- runtime ----------
FROM node:${NODE_VERSION}-slim AS runtime

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# Non-root user
RUN useradd --system --create-home --uid 1001 dashboard

COPY --from=builder --chown=1001:1001 /app/public ./public
COPY --from=builder --chown=1001:1001 /app/.next ./.next
COPY --from=builder --chown=1001:1001 /app/node_modules ./node_modules
COPY --from=builder --chown=1001:1001 /app/package.json ./package.json

USER dashboard
EXPOSE 3000

CMD ["npx", "next", "start", "-p", "3000", "-H", "0.0.0.0"]
