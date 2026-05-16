// Typing Indicator Component

import { motion } from 'framer-motion';

export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="flex flex-col gap-1.5 max-w-[800px] self-start items-start"
    >
      <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
        <span>🧠 MemoryThread AI</span>
        <span>thinking…</span>
      </div>

      <div className="px-4 py-4 rounded-xl text-sm bg-[var(--color-msg-ai)] border border-[var(--color-border-subtle)] rounded-bl-sm flex gap-1.5">
        <motion.div
          className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-primary)]"
          animate={{ y: [0, -6, 0], opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: 0 }}
        />
        <motion.div
          className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-primary)]"
          animate={{ y: [0, -6, 0], opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
        />
        <motion.div
          className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-primary)]"
          animate={{ y: [0, -6, 0], opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}
        />
      </div>
    </motion.div>
  );
}