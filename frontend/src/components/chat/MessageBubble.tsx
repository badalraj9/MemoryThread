import { AnimatePresence, motion } from 'framer-motion';
import type { ChatMessage } from '../../api/types';
import { formatTime } from '../../lib/utils';
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface MessageBubbleProps {
  message: ChatMessage;
}

const bubbleVariants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [memoriesExpanded, setMemoriesExpanded] = useState(false);

  return (
    <motion.div
      initial="initial"
      animate="animate"
      exit="exit"
      variants={bubbleVariants}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col gap-2 w-full"
    >
      {/* Timestamp */}
      <div className={`text-[10px] font-mono text-tertiary ${isUser ? 'text-right' : 'text-left'}`}>
        {formatTime(message.timestamp)}
      </div>

      {/* Message content */}
      <div
        className={`text-[14px] leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? 'ml-auto max-w-[75%] px-4 py-3 border border-subtle rounded text-right text-primary'
            : 'mr-auto max-w-[90%] text-primary border-l-2 border-accent/20 pl-4'
        }`}
      >
        {message.content}
      </div>

      {/* Recalled memories — inline footnote style */}
      {!isUser && message.memories && message.memories.length > 0 && (
        <div className="mr-auto max-w-[90%] pl-4">
          <button
            onClick={() => setMemoriesExpanded(!memoriesExpanded)}
            className="flex items-center gap-2 text-[11px] font-mono text-tertiary hover:text-secondary transition-colors cursor-pointer py-1"
          >
            {memoriesExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Recalled ({message.memories.length})
          </button>
          <AnimatePresence>
            {memoriesExpanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="border border-subtle rounded mt-1 divide-y divide-subtle">
                  {message.memories.map((m) => (
                    <div key={m.id} className="px-3 py-2 text-[11px] font-mono flex items-center justify-between gap-4">
                      <span className="text-secondary truncate">{m.content.split('\n')[0]}</span>
                      <span className="text-tertiary shrink-0">{m.source}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}