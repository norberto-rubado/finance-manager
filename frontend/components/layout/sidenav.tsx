'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  ListOrdered,
  Upload,
  Wallet,
  Tags,
  Filter,
  Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const NAV = [
  { href: '/', label: '首页', icon: Home },
  { href: '/transactions', label: '交易', icon: ListOrdered },
  { href: '/statements', label: '导入', icon: Upload },
  { href: '/accounts', label: '账户', icon: Wallet },
  { href: '/categories', label: '分类', icon: Tags },
  { href: '/rules', label: '规则', icon: Filter },
  { href: '/settings', label: '设置', icon: Settings },
] as const;

export function Sidenav() {
  const pathname = usePathname();
  return (
    <nav className="hidden w-56 flex-col border-r bg-card md:flex" aria-label="主导航">
      <div className="flex h-14 items-center border-b px-4 font-semibold">Finance</div>
      <ul className="flex-1 space-y-1 p-2">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active =
            pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-secondary font-medium'
                    : 'text-muted-foreground hover:bg-secondary/50',
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
