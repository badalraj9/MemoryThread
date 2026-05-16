// Command Palette - Ctrl+K style

import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Command, Search, Settings, Download, Trash2 } from 'lucide-react';

interface CommandItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  shortcut?: string;
  action: () => void;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
  onClear: () => void;
  onExport: (format: 'md' | 'json') => void;
  onOpenSettings: () => void;
}

export function CommandPalette({
  isOpen,
  onOpen,
  onClose,
  onClear,
  onExport,
  onOpenSettings,
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands: CommandItem[] = [
    { id: 'search', label: 'Search memories', icon: <Search className="w-4 h-4" />, shortcut: '⌘K', action: onOpen },
    { id: 'clear', label: 'Clear all memories', icon: <Trash2 className="w-4 h-4" />, action: onClear },
    { id: 'export-md', label: 'Export as Markdown', icon: <Download className="w-4 h-4" />, action: () => onExport('md') },
    { id: 'export-json', label: 'Export as JSON', icon: <Download className="w-4 h-4" />, action: () => onExport('json') },
    { id: 'settings', label: 'Open settings', icon: <Settings className="w-4 h-4" />, shortcut: '⌘,', action: onOpenSettings },
  ];

  const filteredCommands = query
    ? commands.filter(cmd => cmd.label.toLowerCase().includes(query.toLowerCase()))
    : commands;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        isOpen ? onClose : onOpen();
      }
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onOpen, onClose]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filteredCommands[selectedIndex]) {
      e.preventDefault();
      filteredCommands[selectedIndex].action();
      onClose();
    }
  }, [filteredCommands, selectedIndex, onClose]);

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={onOpen}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] text-[var(--color-text-secondary)] text-xs hover:border-[var(--color-neon-cyan)] hover:text-[var(--color-neon-cyan)] transition-all"
      >
        <Command className="w-3 h-3" />
        <span>Search...</span>
        <kbd className="ml-2 px-1.5 py-0.5 rounded bg-[var(--color-bg-surface-hover)] text-[10px]">⌘K</kbd>
      </button>

      {/* Palette overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -20 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-lg bg-[var(--color-bg-surface)] border border-[var(--color-neon-cyan)]/30 rounded-lg shadow-[0_0_40px_rgba(0,248,255,0.2)] overflow-hidden"
            >
              {/* Search input */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border-subtle)]">
                <Search className="w-4 h-4 text-[var(--color-neon-cyan)]" />
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type a command or search..."
                  className="flex-1 bg-transparent text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none text-sm"
                />
                <kbd className="px-1.5 py-0.5 rounded bg-[var(--color-bg-surface-hover)] text-[10px] text-[var(--color-text-tertiary)]">ESC</kbd>
              </div>

              {/* Command list */}
              <div className="max-h-64 overflow-y-auto py-2">
                {filteredCommands.length === 0 ? (
                  <div className="px-4 py-8 text-center text-[var(--color-text-tertiary)] text-sm">
                    No results found
                  </div>
                ) : (
                  filteredCommands.map((cmd, index) => (
                    <button
                      key={cmd.id}
                      onClick={() => {
                        cmd.action();
                        onClose();
                      }}
                      className={`w-full flex items-center justify-between px-4 py-2.5 text-left transition-colors ${
                        index === selectedIndex
                          ? 'bg-[var(--color-neon-cyan)]/10 text-[var(--color-neon-cyan)]'
                          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-surface-hover)]'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className={index === selectedIndex ? 'text-[var(--color-neon-cyan)]' : 'text-[var(--color-text-tertiary)]'}>
                          {cmd.icon}
                        </span>
                        <span className="text-sm">{cmd.label}</span>
                      </div>
                      {cmd.shortcut && (
                        <kbd className="px-1.5 py-0.5 rounded bg-[var(--color-bg-surface-hover)] text-[10px] text-[var(--color-text-tertiary)]">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  ))
                )}
              </div>

              {/* Footer hints */}
              <div className="flex items-center gap-4 px-4 py-2 border-t border-[var(--color-border-subtle)] text-[10px] text-[var(--color-text-tertiary)]">
                <span className="flex items-center gap-1">
                  <kbd className="px-1 py-0.5 rounded bg-[var(--color-bg-surface-hover)]">↑↓</kbd> Navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1 py-0.5 rounded bg-[var(--color-bg-surface-hover)]">↵</kbd> Select
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1 py-0.5 rounded bg-[var(--color-bg-surface-hover)]">esc</kbd> Close
                </span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}