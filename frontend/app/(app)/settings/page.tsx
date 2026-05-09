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
      <ChangePasswordForm />
      <TokenPlaceholderCard />
    </div>
  );
}
