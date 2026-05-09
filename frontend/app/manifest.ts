import type { MetadataRoute } from 'next';

/**
 * PWA-style manifest(Next.js App Router 推荐方式)。
 *
 * 输出到 `/manifest.webmanifest`,layout.tsx 的 `metadata.manifest` 会引用它。
 * MVP 不带自定义图标(`icons: []`),Lighthouse 也只检查 manifest 存在 + name + short_name + display + start_url。
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Finance Manager',
    short_name: 'Finance',
    start_url: '/',
    display: 'standalone',
    background_color: '#0a0a0a',
    theme_color: '#0a0a0a',
    icons: [],
  };
}
