// AppShell Component - Sci-punk style

import type { ReactNode } from 'react';
import { Header } from './Header';

interface AppShellProps {
  children: ReactNode;
  onClear: () => void;
  onOpenSettings: () => void;
  isClearing?: boolean;
}

export function AppShell({ children, onClear, onOpenSettings, isClearing }: AppShellProps) {
  return (
    <div className="flex flex-col h-full w-full bg-[var(--color-bg-base)] relative overflow-hidden">
      {/* Subtle grid background */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(0,248,255,0.03),transparent_70%)]" />
      
      <Header 
        onClear={onClear} 
        onOpenSettings={onOpenSettings}
        isClearing={isClearing} 
      />
      <main className="flex flex-1 overflow-hidden relative">
        {children}
      </main>
    </div>
  );
}