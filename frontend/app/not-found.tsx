import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-semibold">404 — 页面不存在</h1>
      <Button asChild>
        <Link href="/">回首页</Link>
      </Button>
    </div>
  );
}
