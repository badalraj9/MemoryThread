import { type ReactNode } from 'react';
import { LeftRail } from './LeftRail';
import { TopHeader } from './TopHeader';
import { BottomStatus } from './BottomStatus';
import type { SystemStats } from '../../api/types';

interface ResizablePanelLayoutProps {
  chatPanel: ReactNode;
  memoryPanel: ReactNode;
  onClear: () => void;
  onOpenSettings: () => void;
  isClearing?: boolean;
  stats?: SystemStats;
}

export function ResizablePanelLayout({
  chatPanel,
  memoryPanel,
  onClear,
  onOpenSettings,
  isClearing,
  stats,
}: ResizablePanelLayoutProps) {
  return (
    <div className="flex flex-col h-full w-full bg-base text-primary overflow-hidden relative">
      {/* Ambient dot field */}
      <div className="ambient-field absolute inset-0 pointer-events-none z-0" />

      {/* Top header bar */}
      <TopHeader stats={stats} />

      {/* Body: left rail + chat + memory inspector */}
      <div className="flex flex-1 overflow-hidden relative z-10">
        {/* Fixed left icon rail */}
        <LeftRail onClear={onClear} onOpenSettings={onOpenSettings} isClearing={isClearing} />

        {/* Chat area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {chatPanel}
        </div>

        {/* Memory Inspector */}
        {memoryPanel}
      </div>

      {/* Terminal status bar */}
      <BottomStatus stats={stats} />
    </div>
  );
}