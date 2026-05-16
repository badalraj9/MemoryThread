// Memory Comparison Component

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, GitCompare } from 'lucide-react';
import type { Memory } from '../../api/types';
import { Button } from '../ui/Button';
import { formatPercent, formatTruthScore } from '../../lib/utils';

interface MemoryComparisonProps {
  memories: Memory[];
}

export function MemoryComparison({ memories }: MemoryComparisonProps) {
  const [selected, setSelected] = useState<[string, string] | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  if (memories.length < 2) return null;

  const toggleSelection = (id: string) => {
    if (!selected) {
      setSelected([id, '']);
    } else if (selected[0] === id) {
      setSelected(null);
    } else {
      setSelected([selected[0], id]);
    }
  };

  const compareMemories = () => {
    if (selected && selected[0] && selected[1]) {
      setIsOpen(true);
    }
  };

  const closeComparison = () => {
    setIsOpen(false);
    setSelected(null);
  };

  return (
    <div className="p-3 border-t border-[var(--color-border-subtle)]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-[var(--color-text-secondary)]">
          Compare Memories
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={compareMemories}
          disabled={!selected || !selected[1]}
        >
          <GitCompare className="w-3 h-3 mr-1" />
          Compare
        </Button>
      </div>

      <div className="flex flex-wrap gap-1">
        {memories.slice(0, 4).map((m) => (
          <button
            key={m.id}
            onClick={() => toggleSelection(m.id)}
            className={`text-[10px] px-2 py-1 rounded border transition-colors ${
              selected?.[0] === m.id
                ? 'bg-[var(--color-accent-primary)]/20 border-[var(--color-accent-primary)] text-[var(--color-accent-primary)]'
                : 'bg-[var(--color-bg-surface-raised)] border-[var(--color-border-subtle)] text-[var(--color-text-tertiary)] hover:border-[var(--color-border-default)]'
            }`}
          >
            {m.id.substring(0, 6)}…
          </button>
        ))}
      </div>

      <AnimatePresence>
        {isOpen && selected && selected[0] && selected[1] && (
          <ComparisonModal
            memoryA={memories.find((m) => m.id === selected[0])!}
            memoryB={memories.find((m) => m.id === selected[1])!}
            onClose={closeComparison}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function ComparisonModal({
  memoryA,
  memoryB,
  onClose,
}: {
  memoryA: Memory;
  memoryB: Memory;
  onClose: () => void;
}) {
  const fields: { label: string; getValue: (m: Memory) => string | number }[] = [
    { label: 'Truth Score', getValue: (m) => m.truth_score },
    { label: 'Confidence', getValue: (m) => m.confidence },
    { label: 'Authority', getValue: (m) => m.authority },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-[var(--color-bg-surface)] border border-[var(--color-border-subtle)] rounded-lg shadow-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border-subtle)]">
          <h3 className="font-semibold text-[var(--color-text-primary)]">
            Memory Comparison
          </h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 p-4">
          <div>
            <div className="text-xs text-[var(--color-text-tertiary)] mb-2">
              Memory A
            </div>
            <div className="text-sm text-[var(--color-text-primary)] mb-3 line-clamp-3">
              {memoryA.content}
            </div>
          </div>
          <div>
            <div className="text-xs text-[var(--color-text-tertiary)] mb-2">
              Memory B
            </div>
            <div className="text-sm text-[var(--color-text-primary)] mb-3 line-clamp-3">
              {memoryB.content}
            </div>
          </div>
        </div>

        <div className="px-4 pb-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border-subtle)]">
                <th className="text-left py-2 text-[var(--color-text-tertiary)]">Metric</th>
                <th className="text-right py-2 text-[var(--color-text-tertiary)]">A</th>
                <th className="text-right py-2 text-[var(--color-text-tertiary)]">B</th>
                <th className="text-right py-2 text-[var(--color-text-tertiary)]">Diff</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => {
                const valA = field.getValue(memoryA);
                const valB = field.getValue(memoryB);
                const diff =
                  typeof valA === 'number' && typeof valB === 'number'
                    ? valA - valB
                    : 0;
                const diffStr =
                  typeof diff === 'number'
                    ? diff > 0
                      ? `+${diff.toFixed(2)}`
                      : diff.toFixed(2)
                    : '-';
                const winner =
                  typeof diff === 'number' ? (diff > 0 ? 'A' : diff < 0 ? 'B' : '-') : '-';

                return (
                  <tr
                    key={field.label}
                    className="border-b border-[var(--color-border-subtle)]"
                  >
                    <td className="py-2 text-[var(--color-text-secondary)]">
                      {field.label}
                    </td>
                    <td className="text-right py-2 text-[var(--color-text-primary)] font-mono">
                      {typeof valA === 'number' && field.label !== 'Truth Score'
                        ? formatPercent(valA)
                        : formatTruthScore(valA as number)}
                    </td>
                    <td className="text-right py-2 text-[var(--color-text-primary)] font-mono">
                      {typeof valB === 'number' && field.label !== 'Truth Score'
                        ? formatPercent(valB)
                        : formatTruthScore(valB as number)}
                    </td>
                    <td
                      className={`text-right py-2 font-mono ${
                        winner === 'A'
                          ? 'text-[var(--color-truth-high)]'
                          : winner === 'B'
                          ? 'text-[var(--color-accent-primary)]'
                          : 'text-[var(--color-text-tertiary)]'
                      }`}
                    >
                      {diffStr} ({winner})
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </motion.div>
  );
}