import type { Memory } from '../../api/types';
import { formatTimestamp } from '../../lib/utils';

interface MemoryCardProps {
  memory: Memory;
}

export function MemoryCard({ memory }: MemoryCardProps) {
  const truthPercent = Math.min(100, (memory.truth_score / 4.0) * 100);

  return (
    <div className="py-3 border-b border-subtle group hover:bg-surface/50 transition-colors">
      <div className="flex justify-between items-baseline gap-4 mb-2">
        <div className="text-[13px] leading-relaxed text-primary break-words flex-1">
          {memory.content.split('\n')[0]}
        </div>
        <div className="text-[10px] font-mono text-tertiary shrink-0 text-right">
          <div>{memory.source}</div>
          <div>{formatTimestamp(memory.timestamp)}</div>
        </div>
      </div>
      
      <div className="flex items-center gap-4 mt-3">
        <div className="text-[10px] font-mono text-secondary w-[80px]">Truth Score</div>
        <div className="flex-1 h-[2px] bg-[var(--color-truth-track)] relative">
          <div
            className="absolute left-0 top-0 bottom-0 bg-[var(--color-truth-fill)] transition-all duration-500 ease-out"
            style={{ width: `${truthPercent}%` }}
          />
        </div>
        <div className="text-[10px] font-mono text-primary w-[30px] text-right">
          {memory.truth_score.toFixed(2)}
        </div>
      </div>
      <div className="flex gap-4 mt-2 text-[10px] font-mono text-tertiary">
        <div><span className="text-accent">•</span> {(memory.confidence * 100).toFixed(0)}% confidence</div>
        <div className="text-subtle">|</div>
        <div><span className="text-accent">•</span> {(memory.authority * 100).toFixed(0)}% authority</div>
      </div>
    </div>
  );
}