// Keyboard Shortcuts Hook

import { useEffect, useCallback } from 'react';

interface KeyboardShortcut {
  key: string;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  metaKey?: boolean;
  handler: (e: KeyboardEvent) => void;
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      for (const shortcut of shortcuts) {
        const ctrlMatch = shortcut.ctrlKey ? e.ctrlKey || e.metaKey : true;
        const shiftMatch = shortcut.shiftKey ? e.shiftKey : true;
        const metaMatch = shortcut.metaKey ? e.metaKey : true;

        if (
          e.key === shortcut.key &&
          ctrlMatch &&
          shiftMatch &&
          metaMatch &&
          !e.target?.toString().includes('input') &&
          !e.target?.toString().includes('textarea')
        ) {
          e.preventDefault();
          shortcut.handler(e);
          return;
        }
      }
    },
    [shortcuts]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

export function useInputKeyboardShortcuts(
  onSend: () => void,
  onNewLine: () => void
) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLTextAreaElement | HTMLInputElement;
      const isInput = target.tagName === 'TEXTAREA' || target.tagName === 'INPUT';

      if (!isInput) return;

      if (e.key === 'Enter' && !e.shiftKey && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onSend();
      } else if (e.key === 'Enter' && e.shiftKey) {
        onNewLine();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onSend, onNewLine]);
}