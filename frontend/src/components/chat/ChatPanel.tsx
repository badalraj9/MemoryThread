import { AnimatePresence, motion } from 'framer-motion';
import type { ChatMessage } from '../../api/types';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { EmptyChat } from './EmptyChat';
import { TypingIndicator } from './TypingIndicator';

interface ChatPanelProps {
  messages: ChatMessage[];
  onSend: (message: string) => void;
  isLoading?: boolean;
}

export function ChatPanel({ messages, onSend, isLoading }: ChatPanelProps) {
  const isStarted = messages.length > 0 || isLoading;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-transparent">
      {/* Scrollable message area — centered column */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[800px] mx-auto w-full h-full">
          <AnimatePresence mode="wait">
            {!isStarted ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.35 }}
                className="h-full flex flex-col"
              >
                <EmptyChat onSuggestionClick={onSend} />
              </motion.div>
            ) : (
              <motion.div
                key="chat"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="min-h-full"
              >
                <MessageList messages={messages} showTyping={isLoading} />
                <AnimatePresence>
                  {isLoading && <TypingIndicator key="typing" />}
                </AnimatePresence>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Input bar — always pinned at bottom, centered */}
      <motion.div
        className="max-w-[800px] mx-auto w-full px-6 py-4 shrink-0"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.6, ease: 'easeOut' }}
      >
        <MessageInput onSend={onSend} isLoading={isLoading} />
      </motion.div>
    </div>
  );
}