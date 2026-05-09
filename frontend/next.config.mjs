/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // standalone 输出 = `.next/standalone/server.js` 自包含 Node bundle,docker runner stage
  // 只 COPY standalone + static + public,镜像不带 node_modules 体积小。
  //
  // 仅在显式设 `NEXT_OUTPUT_STANDALONE=1` 时启用 —— Windows 本地 `pnpm build` 默认走标准
  // 输出,因为 standalone 模式要求 NTFS symlink (开发者模式 / 管理员才能创建);Dockerfile
  // 在 Linux builder stage 自带该 env(见 frontend/Dockerfile),不影响 prod 构建。
  output: process.env.NEXT_OUTPUT_STANDALONE === '1' ? 'standalone' : undefined,
  experimental: {
    typedRoutes: false,
  },
  // 开发期把 /api/* 代理到 backend(避开 cookie 跨域)
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;
