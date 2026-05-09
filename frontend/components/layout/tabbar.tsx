'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, ListOrdered, Upload, Wallet, MoreHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const TABS = [
  { href: '/', label: '首页', icon: Home },
  { href: '/transactions', label: '交易', icon: ListOrdered },
  { href: '/statements', label: '导入', icon: Upload },
  { href: '/accounts', label: '账户', icon: Wallet },
  { href: '/settings', label: '更多', icon: MoreHorizontal },
] as const;

export function Tabbar() {
  const pathname = usePathname();
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 flex h-14 border-t bg-card md:hidden"
      aria-label="主导航"
    >
      {TABS.map((t) => {
        const Icon = t.icon;
        const active = pathname === t.href || (t.href !== '/' && pathname.startsWith(t.href));
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              'flex flex-1 flex-col items-center justify-center gap-0.5 text-xs',
              active ? 'text-primary' : 'text-muted-foreground',
            )}
          >
            <Icon className="h-5 w-5" />
            <span>{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
