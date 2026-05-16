// Chat Store

import { create } from 'zustand';
import type { ChatMessage, Memory, SystemStats, ChatStats } from '../api/types';

interface ChatStore {
  messages: ChatMessage[];
  recalledMemories: Memory[];
  contextUsed: string;
  lastStats: ChatStats | null;
  systemStats: SystemStats | undefined;
  searchResults: Memory[];
  
  addUserMessage: (content: string) => void;
  addAssistantMessage: (content: string, memories: Memory[], context: string, model: string, entityId: string, stats: ChatStats) => void;
  setRecalledMemories: (memories: Memory[]) => void;
  setContextUsed: (context: string) => void;
  setSystemStats: (stats: SystemStats) => void;
  setSearchResults: (results: Memory[]) => void;
  clear: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  recalledMemories: [],
  contextUsed: '',
  lastStats: null,
  systemStats: undefined,
  searchResults: [],

  addUserMessage: (content: string) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: crypto.randomUUID(),
          role: 'user',
          content,
          timestamp: new Date().toISOString(),
        },
      ],
    })),

  addAssistantMessage: (content, memories, context, model, entityId, stats) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content,
          timestamp: new Date().toISOString(),
          memories,
          context_used: context,
          model,
          entity_id: entityId,
          stats,
        },
      ],
      recalledMemories: memories,
      contextUsed: context,
      lastStats: stats,
    })),

  setRecalledMemories: (memories) => set({ recalledMemories: memories }),
  setContextUsed: (context) => set({ contextUsed: context }),
  setSystemStats: (stats) => set({ systemStats: stats }),
  setSearchResults: (results) => set({ searchResults: results }),
  clear: () =>
    set({
      messages: [],
      recalledMemories: [],
      contextUsed: '',
      lastStats: null,
      searchResults: [],
    }),
}));