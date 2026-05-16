import { useState, useCallback } from 'react';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ResizablePanelLayout } from './components/layout/ResizablePanelLayout';
import { ChatPanel } from './components/chat/ChatPanel';
import { MemoryPanel } from './components/memory/MemoryPanel';
import { Settings } from './components/settings/Settings';
import { ToastContainer } from './components/ui/Toast';
import { useChatMutation } from './api/chat';
import { useStats, useRecall, useClear } from './api/memories';
import { useChatStore } from './stores/chatStore';
import { toast } from './stores/toastStore';
import { exportAsMarkdown, exportAsJSON, downloadFile } from './lib/export';

function AppContent() {
  const [isTyping, setIsTyping] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState({
    autoRecall: false,
    topK: 8,
    namespace: 'mt_chat',
  });

  const {
    messages,
    recalledMemories: memories,
    contextUsed: context,
    searchResults,
    addUserMessage,
    addAssistantMessage,
    setSearchResults,
    clear: clearStore,
  } = useChatStore();

  const chatMutation = useChatMutation();
  const { data: stats } = useStats();
  const recallMutation = useRecall();
  const clearMutation = useClear();

  const handleSend = useCallback(async (text: string) => {
    addUserMessage(text);
    setIsTyping(true);

    try {
      const response = await chatMutation.mutateAsync({ message: text });
      
      addAssistantMessage(
        response.answer,
        response.memories,
        response.context_used,
        response.model,
        response.entity_id,
        response.stats
      );
    } catch (error) {
      addAssistantMessage(
        `⚠️ Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        [],
        '',
        '',
        '',
        { recall_time_ms: 0, tokens_used: 0, memories_considered: 0 }
      );
      toast.error('Chat request failed');
    } finally {
      setIsTyping(false);
    }
  }, [chatMutation, addUserMessage, addAssistantMessage]);

  const handleSearch = useCallback(async (query: string) => {
    try {
      const response = await recallMutation.mutateAsync({
        query,
        top_k: settings.topK,
      });
      setSearchResults(response.memories);
    } catch (error) {
      console.error('Search error:', error);
      toast.error('Search failed');
    }
  }, [recallMutation, settings.topK, setSearchResults]);

  const handleClear = useCallback(async () => {
    if (!confirm('Clear all in-memory memories? (Postgres/Qdrant data persists unless you also drop tables)')) {
      return;
    }

    try {
      await clearMutation.mutateAsync();
      clearStore();
      toast.success('Memories cleared');
    } catch (error) {
      console.error('Clear error:', error);
      toast.error('Failed to clear memories');
    }
  }, [clearMutation, clearStore]);

  const handleExport = useCallback((format: 'md' | 'json') => {
    const content = format === 'md' 
      ? exportAsMarkdown(messages, memories)
      : exportAsJSON(messages, memories);
    const filename = `memorythread-export-${Date.now()}.${format}`;
    downloadFile(content, filename, format === 'md' ? 'text/markdown' : 'application/json');
    toast.success(`Exported as ${format.toUpperCase()}`);
  }, [messages, memories]);

  const handleConfigChange = useCallback((config: Partial<typeof settings>) => {
    setSettings((prev) => ({ ...prev, ...config }));
  }, []);

  return (
    <ErrorBoundary>
      <ResizablePanelLayout
        chatPanel={
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            isLoading={isTyping}
          />
        }
        memoryPanel={
          <MemoryPanel
            memories={memories}
            context={context}
            stats={stats}
            onSearch={handleSearch}
            searchResults={searchResults}
            isSearching={recallMutation.isPending}
            onOpenSettings={() => setSettingsOpen(true)}
          />
        }
        onClear={handleClear}
        onOpenSettings={() => setSettingsOpen(true)}
        isClearing={clearMutation.isPending}
        stats={stats}
      />
      <Settings
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        config={settings}
        onConfigChange={handleConfigChange}
        onExport={handleExport}
        onReset={handleClear}
      />
      <ToastContainer />
    </ErrorBoundary>
  );
}

export default function App() {
  return <AppContent />;
}