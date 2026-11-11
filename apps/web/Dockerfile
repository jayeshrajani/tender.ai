# syntax=docker/dockerfile:1
# Build context: repository root.
FROM node:22-alpine AS deps
WORKDIR /repo
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter @tenderos/web

FROM deps AS build
ARG TENDEROS_API_INTERNAL_URL=http://api:8000
ENV TENDEROS_API_INTERNAL_URL=$TENDEROS_API_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
COPY apps/web apps/web
RUN pnpm --filter @tenderos/web build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S tenderos && adduser -S tenderos -G tenderos
COPY --from=build --chown=tenderos /repo/apps/web/.next/standalone ./
COPY --from=build --chown=tenderos /repo/apps/web/.next/static ./apps/web/.next/static
USER tenderos
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
