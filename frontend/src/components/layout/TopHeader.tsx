import type { SystemStats } from '../../api/types';
import { useStats } from '../../api/memories';

interface TopHeaderProps {
  stats?: SystemStats;
}

function StatusDot({ connected, label }: { connected: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] font-mono text-secondary">
      <span>{label}</span>
      <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-accent' : 'bg-red-500'}`} />
    </div>
  );
}

export function TopHeader({ stats }: TopHeaderProps) {
  const { data: liveStats } = useStats();
  const s = liveStats ?? stats;

  return (
    <div className="h-[44px] border-b border-subtle bg-base flex items-center px-5 gap-6 shrink-0 z-10">
      {/* Logo */}
      <div className="flex items-center gap-2 text-[13px] font-medium text-primary mr-4">
        <span>🧵</span>
        <span>MemoryThread</span>
        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-system-pulse ml-1" />
      </div>

      {/* Connection status */}
      <StatusDot connected={true} label="PostgreSQL" />
      <StatusDot connected={!!s?.qdrant_connected} label="Qdrant" />
    </div>
  );
}
