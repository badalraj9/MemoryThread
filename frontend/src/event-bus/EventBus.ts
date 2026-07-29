import type { DeltaPayload, GoldenThreadNode, GraphEdge, GraphNode } from '../types/graph'

export type EventMap = {
  // Search
  SearchStarted: { query: string }
  SearchCompleted: { query: string; results: Array<{ nodeId: string; score: number }> }

  // Selection & Hover
  NodeHovered: { nodeId: string | null }
  NodeSelected: { nodeId: string }
  NodeDeselected: undefined

  // Activation & Signal Wave Surges
  ActivationStarted: { seedIds: string[] }
  ActivationWave: { nodeId: string; intensity: number; delayMs: number }
  ActivationFinished: undefined

  // Golden Thread & Causality
  GoldenThreadRequested: { nodeId: string }
  GoldenThreadReceived: { nodeId: string; thread: GoldenThreadNode[] }

  // Graph Mutations & SSE Delta Synchronization
  NodeAdded: { node: GraphNode }
  NodeUpdated: { node: GraphNode }
  NodeRemoved: { nodeId: string }
  EdgeAdded: { edge: GraphEdge }
  EdgeRemoved: { source: string; target: string }
  DeltaReceived: DeltaPayload
  SSEReconnected: undefined
  SSEDisconnected: undefined

  // Agent Cognitive Traces
  AgentActivityPulse: { nodeId: string; intensity: number; type: string }
  AgentRecallBurst: { nodeIds: string[] }
  AgentTraversalPath: { nodeIds: string[]; edgeIds?: string[] }

  // Cognitive State Events
  ContradictionDetected: { sourceId: string; targetId: string; severity: number }
  MergeStarted: { sourceId: string; targetId: string }
  MergeFinished: { survivingId: string }

  // Camera Focus
  CameraFocusRequested: { nodeIds: string[]; duration?: number }
  CameraResetRequested: undefined

  // Inspector
  InspectorClosed: undefined
}

type EventKey = keyof EventMap
type EventCallback<K extends EventKey> = (data: EventMap[K]) => void

class EventBus {
  private listeners: Map<EventKey, Array<(data: any) => void>> = new Map()

  on<K extends EventKey>(event: K, callback: EventCallback<K>): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, [])
    }
    this.listeners.get(event)!.push(callback)
  }

  off<K extends EventKey>(event: K, callback: EventCallback<K>): void {
    const list = this.listeners.get(event)
    if (!list) return
    this.listeners.set(
      event,
      list.filter((cb) => cb !== callback),
    )
  }

  emit<K extends EventKey>(event: K, data: EventMap[K]): void {
    const list = this.listeners.get(event)
    if (!list) return
    for (const callback of list) {
      try {
        callback(data)
      } catch (error) {
        console.error(`Error handling event ${String(event)}:`, error)
      }
    }
  }
}

export const eventBus = new EventBus()
