FROM node:20-alpine AS builder
WORKDIR /app

COPY src/frontend/package*.json ./
RUN npm ci

COPY src/frontend .

# NEXT_PUBLIC_* se interpola en build time para el HTML pre-renderizado.
# Pasar via build-arg desde docker-compose.yml.
ARG NEXT_PUBLIC_SITE_URL=
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL

RUN npm run build

# ─────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# node:20-alpine ships a non-root `node` user (uid 1000)
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node

EXPOSE 3001
ENV PORT=3001
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
