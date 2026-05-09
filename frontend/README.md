# Finance Manager — Frontend

Next.js 14 + TypeScript + Tailwind + shadcn/ui。前后端分离,backend 在 `:8000`,前端 `:3000`。

## 开发

```powershell
pnpm install                  # 装依赖
pnpm dev                      # 开发服务器(:3000)
pnpm typecheck                # 类型检查
pnpm lint                     # ESLint
pnpm test:unit                # Vitest
pnpm test:e2e                 # Playwright(需 backend + db 起着)
pnpm build                    # 生产构建
```

## 路由

见 `app/`。`/login` 公开;其余 `(app)/*` 由 `middleware.ts` 保护(无 `fm_session` cookie 跳 login)。

## 与 backend 联调

dev 模式下 `next.config.mjs` 把 `/api/*` rewrite 到 `http://localhost:8000/api/*`,cookie 自动复用同 origin。生产由 Caddy 反代。
