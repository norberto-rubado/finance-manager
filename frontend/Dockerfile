# Multi-stage Next.js production build,供 slice E `docker-compose --profile prod` 用。
# 本切片 (D) dev 模式直接 `pnpm dev`,不依赖此 Dockerfile;但 standalone 输出依赖
# next.config.mjs 里 `output: 'standalone'`(已设)。

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@9 --activate && pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.mjs 默认走标准输出(避免 Windows symlink 问题);docker build
# 在 Linux 上明确开启 standalone 让 runner stage 可以薄部署。
ENV NEXT_OUTPUT_STANDALONE=1
RUN corepack enable && corepack prepare pnpm@9 --activate && pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
