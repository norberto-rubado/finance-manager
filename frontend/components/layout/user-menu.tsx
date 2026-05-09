'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { LogOut, Settings, User } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { logout, me } from '@/lib/api/auth';

export function UserMenu() {
  const router = useRouter();
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    // Task 22 polish:探测当前用户名时不主动跳 /login —— 否则 token 过期窗口下,
    // UserMenu 会与 (app)/layout.tsx 的路由守卫同时触发跳转,造成跳两次或闪屏。
    me({ redirectOn401: false })
      .then((u) => setUsername(u.username))
      .catch(() => setUsername(null));
  }, []);

  const onLogout = async () => {
    try {
      await logout();
    } catch {
      // 忽略;cookie 已被清(或 401 中间件兜底)
    }
    toast.success('已登出');
    router.push('/login');
    router.refresh();
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="用户菜单">
          <User className="h-5 w-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{username ?? '未登录'}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings" className="flex items-center gap-2">
            <Settings className="h-4 w-4" /> 设置
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onLogout} className="flex items-center gap-2">
          <LogOut className="h-4 w-4" /> 登出
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
