import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PUBLIC_PATHS = ['/login'];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // 静态资源 / Next 内部 / API rewrites 全放行(matcher 已过滤但稳一手)
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname === '/favicon.ico' ||
    pathname.startsWith('/static')
  ) {
    return NextResponse.next();
  }

  // 登录页放行
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
    return NextResponse.next();
  }

  // 检查 fm_session cookie
  const session = req.cookies.get('fm_session');
  if (!session) {
    const loginUrl = new URL('/login', req.url);
    // 保留 from 参数让登录后跳回
    if (pathname !== '/') loginUrl.searchParams.set('from', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // 所有路由除 _next/api/static
    '/((?!_next/static|_next/image|favicon.ico|api).*)',
  ],
};
