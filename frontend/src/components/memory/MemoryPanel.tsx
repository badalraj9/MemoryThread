import { useState } from 'react';
import type { Memory, SystemStats } from '../../api/types';
import { MemoryCard } from './MemoryCard';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { ChevronRight, Database, Search as SearchIcon } from 'lucide-react';

interface MemoryPanelProps {
  memories: Memory[];
  context: string;
  stats: SystemStats | undefined;
  onSearch: (query: string) => void;
  searchResults: Memory[];
  isSearching?: boolean;
  onOpenSettings: () => void;
}

type Tab = 'recall' | 'context' | 'search';

export function MemoryPanel({
  memories,
  context,
  onSearch,
  searchResults,
  isSearching,
}: MemoryPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('recall');
  const [searchQuery, setSearchQuery] = useState('');
  const [isExpanded, setIsExpanded] = useState(true);

  const handleSearch = () => {
    if (searchQuery.trim()) onSearch(searchQuery.trim());
  };

  if (!isExpanded) {
    return (
      <div
        className="w-[40px] hover:w-[56px] h-full border-l border-subtle bg-base hover:bg-surface transition-all duration-300 cursor-pointer flex flex-col items-center py-6 gap-6 text-tertiary hover:text-primary group shrink-0"
        onClick={() => setIsExpanded(true)}
      >
        <div className="flex flex-col gap-5 opacity-30 group-hover:opacity-80 transition-opacity">
          <Database className="w-3.5 h-3.5" />
          <SearchIcon className="w-3.5 h-3.5" />
        </div>
        <div
          className="text-[10px] uppercase tracking-widest font-mono mt-auto mb-4"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          Memory Inspector
        </div>
      </div>
    );
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'recall':
        return memories.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-tertiary text-[11px] p-5 text-center font-mono py-16">
            Memories retrieved per turn<br />will appear here
          </div>
        ) : (
          <div className="flex flex-col px-4 pb-4">
            {memories.map((m) => (
              <MemoryCard key={m.id} memory={m} />
            ))}
          </div>
        );

      case 'context':
        return !context || context === 'No relevant memories found.' ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-tertiary text-[11px] p-5 text-center font-mono py-16">
            LLM context injected<br />will appear here
          </div>
        ) : (
          <div className="p-4 text-[11px] font-mono text-secondary whitespace-pre-wrap leading-relaxed break-words">
            {context}
          </div>
        );

      case 'search':
        return (
          <div className="flex flex-col h-full">
            <div className="p-4 border-b border-subtle">
              <div className="flex gap-2">
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Search memories…"
                  className="flex-1 bg-transparent text-[12px] h-8 font-mono"
                />
                <Button size="sm" variant="outline" onClick={handleSearch} disabled={isSearching} className="h-8 text-[11px] font-mono">
                  Go
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-4 pb-4">
              {searchResults.length === 0 ? (
                <div className="flex flex-col items-center justify-center text-tertiary text-[11px] text-center font-mono py-16">
                  Search the memory store
                </div>
              ) : (
                <div className="flex flex-col">
                  {searchResults.map((m) => (
                    <MemoryCard key={m.id} memory={m} />
                  ))}
                </div>
              )}
            </div>
          </div>
        );
    }
  };

  return (
    <div className="w-[360px] h-full flex flex-col bg-surface border-l border-subtle shrink-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-subtle flex items-center justify-between shrink-0">
        <span className="text-[12px] font-medium text-primary tracking-wide">Memory Inspector</span>
        <button
          onClick={() => setIsExpanded(false)}
          className="flex items-center gap-1 text-[10px] font-mono text-tertiary hover:text-primary transition-colors cursor-pointer"
        >
          <ChevronRight className="w-3 h-3" />
          Collapse
          <span className="ml-1 text-tertiary">⌘ \</span>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-subtle shrink-0 px-4 gap-5">
        {(['recall', 'context', 'search'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`py-2.5 text-[11px] font-mono transition-colors border-b-2 cursor-pointer ${
              activeTab === tab
                ? 'text-accent border-accent'
                : 'text-tertiary border-transparent hover:text-secondary'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto flex flex-col pt-2">
        {renderContent()}
      </div>
    </div>
  );
}