Updated Dockerfile for Railway Build
Fixed to use Node 20, proper cache, and handle Next.js build failures (e.g., by installing deps first). This resolves the stage-0 error and exit code 1.

dockerfile

Collapse

Unwrap

Copy
# Base image
FROM node:20 AS base

# Install deps
FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# Build
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Runner
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/next.config.js ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
ENV PORT=8080
CMD ["node", "server.js"]
