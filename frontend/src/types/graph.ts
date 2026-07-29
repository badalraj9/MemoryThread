export type MemoryType =
  | 'fact'
  | 'event'
  | 'preference'
  | 'identity'
  | 'prediction'
  | 'decision'
  | 'failure'
  | 'workflow'
  | 'belief'

export interface TruthVector {
  confidence: number // 0..1 (Scales density peak)
  authority: number // 0..1 (Shifts color towards Golden Amber)
  freshness: number // 0..1 (Scales temporal decay)
  corroboration: number // 0..1 (Reinforces kernel stability)
  composite: number // 0..1 (Overall score)
}

export interface GraphNode {
  id: string
  label: string
  content: string
  type: MemoryType
  truth: TruthVector
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
  weight?: number
  confidence?: number
  isContradiction?: boolean
}

export interface GoldenThreadNode {
  nodeId: string
  entityId?: string
  actor: string
  action: string
  timestamp: string
  delta?: Record<string, unknown>
}

export interface SearchResult {
  nodeId: string
  score: number
  content?: string
}

export interface DeltaPayload {
  type: 'delta'
  seq: number
  changes: {
    nodes_added?: GraphNode[]
    nodes_removed?: string[]
    nodes_updated?: Partial<GraphNode>[]
    edges_added?: GraphEdge[]
    edges_removed?: string[]
  }
}
