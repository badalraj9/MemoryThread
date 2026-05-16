// MessageList Component with AnimatePresence

import { AnimatePresence } from 'framer-motion';
import type { ChatMessage } from '../../api/types';
import { MessageBubble } from './MessageBubble';
import { EmptyChat } from './EmptyChat';

interface MessageListProps {
  messages: ChatMessage[];
  showTyping?: boolean;
}

export function MessageList({ messages, showTyping }: MessageListProps) {
  if (messages.length === 0 && !showTyping) {
    return <EmptyChat />;
  }

  return (
    <div className="flex flex-col gap-5 p-6">
      <AnimatePresence mode="popLayout">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </AnimatePresence>
    </div>
  );
}