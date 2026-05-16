// API Type Definitions

export interface Memory {
  id: string;
  content: string;
  truth_score: number;
  confidence: number;
  authority: number;
  memory_type: string;
  source: string;
  timestamp: string;
  embedding?: number[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  memories?: Memory[];
  context_used?: string;
  model?: string;
  entity_id?: string;
  stats?: ChatStats;
}

export interface ChatStats {
  recall_time_ms: number;
  tokens_used: number;
  memories_considered: number;
}

export interface SystemStats {
  total_memories: number;
  total_events: number;
  avg_truth_score: number | null;
  qdrant_connected: boolean;
  db_type: string;
  namespace: string;
  throughput_eps?: number;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  model: string;
  entity_id: string;
  memories: Memory[];
  context_used: string;
  stats: ChatStats;
}

export interface RecallRequest {
  query: string;
  top_k?: number;
}

export interface RecallResponse {
  memories: Memory[];
  query_time_ms?: number;
}

export interface StatsResponse extends SystemStats {}

export interface ApiError {
  error: string;
  message?: string;
}