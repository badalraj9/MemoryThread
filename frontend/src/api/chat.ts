// Chat API Hooks

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import { queryKeys } from './keys';
import type { ChatRequest, ChatResponse } from './types';

export const useChatMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ChatRequest) =>
      apiClient.post<ChatResponse>('/chat', data),

    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.stats() });
    },
  });
};