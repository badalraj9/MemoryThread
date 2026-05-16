// Header Component - Sci-punk aesthetic

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { CommandPalette } from '../ui/CommandPalette';
import { useStats } from '../../api/memories';
import type { SystemStats } from '../../api/types';

interface HeaderProps {
  onClear: () => void;
  onOpenSettings: () => void;
  isClearing?: boolean;
}

export function Header({ onClear, onOpenSettings, isClearing }: HeaderProps) {
  const { data: stats, isLoading } = useStats();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  const getStatusPills = (stats: SystemStats | undefined) => {
    if (isLoading || !stats) {
      return (
        <Badge variant="default">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)] animate-pulse" />
          <span>INITIALIZING...</span>
        </Badge>
      );
    }

    return (
      <>
        <Badge variant="success">
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          <span>POSTGRES</span>
        </Badge>
        {stats.qdrant_connected ? (
          <Badge variant="info">
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            <span>QDRANT</span>
          </Badge>
        ) : (
          <Badge variant="warning">
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            <span>QDRANT-OFFLINE</span>
          </Badge>
        )}
        <Badge variant="default">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-neon-violet)]" />
          <span>{stats.namespace?.toUpperCase() || 'MT_CHAT'}</span>
        </Badge>
      </>
    );
  };

  const handleExport = (format: 'md' | 'json') => {
    console.log('Export:', format);
  };

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-[var(--color-bg-glass)] border-b border-[var(--color-neon-cyan)]/20 backdrop-blur-md flex-shrink-0 gap-3 scanlines relative">
      {/* Corner accents */}
      <div className="absolute top-0 left-0 w-2 h-2 border-l border-t border-[var(--color-neon-cyan)]" />
      <div className="absolute top-0 right-0 w-2 h-2 border-r border-t border-[var(--color-neon-cyan)]" />
      <div className="absolute bottom-0 left-0 w-2 h-2 border-l border-b border-[var(--color-neon-cyan)]" />
      <div className="absolute bottom-0 right-0 w-2 h-2 border-r border-b border-[var(--color-neon-cyan)]" />

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          {/* Logo - Glowing orb */}
          <div className="relative w-9 h-9 rounded-md bg-gradient-to-br from-[var(--color-neon-cyan)] to-[var(--color-neon-violet)] flex items-center justify-center animate-glow">
            <span className="text-lg">🧵</span>
            <div className="absolute inset-0 rounded-md animate-pulse" style={{ boxShadow: '0 0 20px var(--color-neon-cyan)' }} />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wider font-[var(--font-display)] text-[var(--color-neon-cyan)]">
              MEMORY_THREAD
            </div>
            <div className="text-[9px] text-[var(--color-text-tertiary)] tracking-[0.2em] uppercase">
              <span className="text-[var(--color-neon-magenta)]">◆</span> Truth-Preserving AI Memory
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Command palette trigger */}
        <CommandPalette
          isOpen={commandPaletteOpen}
          onOpen={() => setCommandPaletteOpen(true)}
          onClose={() => setCommandPaletteOpen(false)}
          onClear={onClear}
          onExport={handleExport}
          onOpenSettings={onOpenSettings}
        />

        {getStatusPills(stats)}
      </div>

      <div className="flex items-center gap-2.5">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClear}
          disabled={isClearing}
          className="border border-transparent hover:border-[var(--color-error)] hover:text-[var(--color-error)]"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span className="text-[10px] tracking-wider">PURGE</span>
        </Button>
      </div>
    </header>
  );
}