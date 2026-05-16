import { motion } from 'framer-motion';

interface EmptyChatProps {
  onSuggestionClick?: (text: string) => void;
}

const suggestions = [
  'Tell me something about you',
  'Store a preference',
  'Test recall system',
  'Inspect memory state'
];

export function EmptyChat({ onSuggestionClick }: EmptyChatProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-10 text-center max-w-[600px] mx-auto h-full w-full">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="flex flex-col gap-3 animate-breathe"
      >
        <div className="text-xl font-medium text-primary tracking-wide">
          MemoryThread
        </div>
        <div className="text-[12px] text-tertiary font-mono uppercase tracking-widest">
          A cognitive memory interface for AI systems
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.15 }}
        className="w-8 h-[1px] bg-subtle my-2"
      />

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.25 }}
        className="text-[13px] text-secondary leading-relaxed max-w-[420px]"
      >
        Each interaction is stored, scored, and retrieved dynamically.<br/>
        This interface exposes memory recall, confidence, and contextual reasoning.
      </motion.div>

      <div className="flex flex-wrap gap-3 justify-center mt-8 max-w-[500px]">
        {suggestions.map((s, i) => (
          <motion.button
            key={s}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.4 + i * 0.1 }}
            whileHover={{ y: -2, scale: 1.02 }}
            onClick={() => onSuggestionClick?.(s)}
            className="px-4 py-2 rounded text-[11px] font-mono border border-subtle text-secondary cursor-pointer transition-all hover:border-accent hover:text-accent hover:bg-surface"
          >
            {s}
          </motion.button>
        ))}
      </div>
    </div>
  );
}