FROM node:22.16.0-alpine3.21 AS dependencies

ENV COREPACK_HOME=/corepack \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN corepack pnpm@10.15.1 install --frozen-lockfile

FROM dependencies AS builder

COPY apps/web ./apps/web
RUN corepack pnpm@10.15.1 --filter @agentos/web build

FROM node:22.16.0-alpine3.21 AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm \
              /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm \
              /usr/local/bin/npx \
              /usr/local/bin/corepack

COPY --from=builder --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static

USER node

EXPOSE 3000

ENV HOSTNAME=0.0.0.0 \
    PORT=3000

CMD ["node", "apps/web/server.js"]
