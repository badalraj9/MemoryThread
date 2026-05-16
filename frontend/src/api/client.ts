// API Client

const API_BASE = '/api';

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

export const apiClient = {
  get: <T>(endpoint: string) => request<T>(endpoint),
  post: <T>(endpoint: string, data?: unknown) => 
    request<T>(endpoint, { 
      method: 'POST', 
      body: data ? JSON.stringify(data) : undefined 
    }),
  put: <T>(endpoint: string, data?: unknown) => 
    request<T>(endpoint, { 
      method: 'PUT', 
      body: data ? JSON.stringify(data) : undefined 
    }),
  delete: <T>(endpoint: string) => 
    request<T>(endpoint, { method: 'DELETE' }),
};