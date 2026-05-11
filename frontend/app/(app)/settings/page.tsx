import Link from 'next/link';
import { Wallet } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ChangePasswordForm } from '@/components/settings/change-password-form';
import { TokenPlaceholderCard } from '@/components/settings/token-placeholder-card';
import { ThemeToggle } from '@/components/layout/theme-toggle';

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">设置</h1>
      <Card>
        <CardHeader>
          <CardTitle>外观</CardTitle>
          <CardDescription>切换暗色/亮色主题(默认暗色)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">点击切换:</span>
            <ThemeToggle />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>预算管理</CardTitle>
          <CardDescription>设置月度总预算与各类别预算</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/settings/budgets">
              <Wallet className="mr-2 h-4 w-4" />
              管理预算
            </Link>
          </Button>
        </CardContent>
      </Card>
      <ChangePasswordForm />
      <TokenPlaceholderCard />
    </div>
  );
}
