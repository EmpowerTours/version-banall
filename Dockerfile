FROM node:20 AS base

FROM base AS deps
WORKDIR /app/farcaster  # Set to subfolder
COPY farcaster/package.json farcaster/package-lock.json* ./
RUN npm ci

FROM base AS builder
WORKDIR /app/farcaster  # Set to subfolder
COPY --from=deps /app/farcaster/node_modules ./node_modules
COPY farcaster/ .
RUN npm run build

FROM base AS runner
WORKDIR /app/farcaster  # Set to subfolder
ENV NODE_ENV=production
COPY --from=builder /app/farcaster/next.config.js ./
COPY --from=builder /app/farcaster/public ./public
COPY --from=builder /app/farcaster/.next/standalone ./
COPY --from=builder /app/farcaster/.next/static ./.next/static
ENV PORT=8080
CMD ["node", "server.js"]
