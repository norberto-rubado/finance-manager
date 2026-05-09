'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';

/**
 * 主题切换按钮。
 *
 * **mounted gate(Task 22 polish):** SSR 阶段拿不到 next-themes 的真实主题,
 * 直接渲染会出现"闪一下亮 → 切到暗"的水合闪烁。先渲染禁用占位(Moon icon),
 * 等 useEffect 跑完才切换到真实图标 + 启用 onClick,消除 hydration mismatch warning。
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // 占位:固定 Moon icon + disabled,保留 size/aria 形状不引发布局抖动
    return (
      <Button
        variant="ghost"
        size="icon"
        aria-label="主题切换"
        disabled
      >
        <Moon className="h-5 w-5" />
      </Button>
    );
  }

  const isDark = theme === 'dark';
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={isDark ? '切换到亮色' : '切换到暗色'}
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
    >
      {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </Button>
  );
}
