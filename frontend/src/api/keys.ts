// Query Keys Factory

export const queryKeys = {
  stats: () => ['stats'] as const,
  chat: (sessionId?: string) => ['chat', sessionId] as const,
  recall: (query: string) => ['recall', query] as const,
  clear: () => ['clear'] as const,
};