import { useState, useRef, type KeyboardEvent, type ChangeEvent, useEffect } from 'react';
import { Send, Paperclip, Code2 } from 'lucide-react';

interface MessageInputProps {
  onSend: (message: string) => void;
  isLoading?: boolean;
}

export function MessageInput({ onSend, isLoading }: MessageInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleAutoResize = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    const text = message.trim();
    if (!text || isLoading) return;
    onSend(text);
    setMessage('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    handleAutoResize();
  };

  return (
    <div className="flex flex-col border border-subtle rounded bg-surface focus-within:border-accent focus-within:shadow-[0_0_20px_rgba(61,214,140,0.08)] transition-all duration-300">
      {/* Text area */}
      <textarea
        ref={textareaRef}
        value={message}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Ask anything about your memories..."
        rows={1}
        className="w-full bg-transparent border-none outline-none resize-none text-[14px] text-primary placeholder:text-tertiary font-mono px-4 pt-4 pb-2 leading-relaxed min-h-[56px] max-h-[160px]"
      />

      {/* Bottom row: icons + send */}
      <div className="flex items-center justify-between px-3 pb-2">
        <div className="flex items-center gap-1 text-tertiary">
          <button className="w-7 h-7 flex items-center justify-center rounded hover:text-secondary transition-colors" title="Attach">
            <Paperclip className="w-3.5 h-3.5" />
          </button>
          <button className="w-7 h-7 flex items-center justify-center rounded hover:text-secondary transition-colors" title="Code block">
            <Code2 className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-tertiary">⌘↵ to send</span>
          <button
            onClick={handleSend}
            disabled={!message.trim() || isLoading}
            className={`w-8 h-8 flex items-center justify-center rounded transition-colors ${
              message.trim() && !isLoading
                ? 'text-accent hover:bg-accent/10 cursor-pointer'
                : 'text-tertiary cursor-default'
            }`}
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}