import { Sidenav } from './sidenav';
import { Tabbar } from './tabbar';
import { UserMenu } from './user-menu';
import { ThemeToggle } from './theme-toggle';

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidenav />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-end gap-1 border-b bg-card/95 px-4 backdrop-blur">
          <ThemeToggle />
          <UserMenu />
        </header>
        <main className="flex-1 overflow-x-hidden p-4 pb-20 md:p-6 md:pb-6">{children}</main>
        <Tabbar />
      </div>
    </div>
  );
}
