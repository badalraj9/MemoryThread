import type { SystemStats } from '../../api/types';

interface BottomStatusProps {
  stats?: SystemStats;
}

export function BottomStatus({ stats }: BottomStatusProps) {
  return (
    <div className="h-[28px] border-t border-subtle bg-base flex items-center px-4 font-mono text-[10px] text-tertiary opacity-70 shrink-0 w-full z-10">
      <div className="flex gap-4 w-full">
        <span>{stats?.total_memories || 0} memories</span>
        <span>·</span>
        <span>{stats?.total_events || 0} events</span>
        <span>·</span>
        <span>{stats?.avg_truth_score?.toFixed(2) || '0.00'} avg truth</span>
        <span className="flex-1"></span>
        <span className="flex items-center gap-1.5">
          Qdrant connected
          <span className={`w-1.5 h-1.5 rounded-full ${stats?.qdrant_connected ? 'bg-status-success' : 'bg-status-error'}`} />
        </span>
      </div>
    </div>
  );
}
