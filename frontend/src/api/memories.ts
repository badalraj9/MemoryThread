// Memories API Hooks

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import { queryKeys } from './keys';
import type { RecallRequest, RecallResponse, StatsResponse } from './types';

export const useStats = () =>
  useQuery({
    queryKey: queryKeys.stats(),
    queryFn: () => apiClient.get<StatsResponse>('/stats'),
    refetchInterval: 30000,
  });

export const useRecall = () =>
  useMutation({
    mutationFn: (data: RecallRequest) =>
      apiClient.post<RecallResponse>('/recall', data),
  });

export const useClear = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: () => apiClient.post('/clear'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: ['recall'] });
    },
  });
};