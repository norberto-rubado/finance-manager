import { Inbox, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

/**
 * 空态占位:icon + title + 可选 description / action。
 * Task 11 列表页 / Task 16 复查页 / Task 17 账单详情等地方共用。
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  className,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  className?: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 py-12 text-center',
        className,
      )}
    >
      <Icon className="h-10 w-10 text-muted-foreground" />
      <h3 className="text-base font-medium">{title}</h3>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
