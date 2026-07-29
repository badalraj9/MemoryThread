import { eventBus } from '../event-bus/EventBus'
import type { DeltaPayload, GraphNode } from '../types/graph'

export interface CognitiveEventPayload {
  type: 'cognitive_event'
  event_type: 'activity_pulse' | 'recall_burst' | 'traversal_path' | 'golden_thread'
  data: {
    nodeId?: string
    intensity?: number
    activity_type?: string
    nodeIds?: string[]
    edgeIds?: string[]
    thread?: any[]
  }
}

export class SSEClient {
  private eventSource: EventSource | null = null
  private reconnectAttempt = 0
  private reconnectTimer: number | null = null
  private url: string | null = null
  private manuallyDisconnected = false

  connect(url: string) {
    this.disconnect()
    this.url = url
    this.manuallyDisconnected = false
    this.open()
  }

  disconnect() {
    this.manuallyDisconnected = true
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.eventSource?.close()
    this.eventSource = null
  }

  private open() {
    if (!this.url) return

    this.eventSource = new EventSource(this.url)

    this.eventSource.onopen = () => {
      this.reconnectAttempt = 0
      eventBus.emit('SSEReconnected', undefined)
    }

    this.eventSource.onmessage = (message) => {
      const payload = JSON.parse(message.data) as unknown
      if (isDeltaPayload(payload)) {
        eventBus.emit('DeltaReceived', payload)
        payload.changes.nodes_added?.forEach((node) => {
          eventBus.emit('NodeAdded', { node })
        })
        payload.changes.nodes_updated?.forEach((node) => {
          if (node.id) {
            eventBus.emit('NodeUpdated', { node: node as GraphNode })
          }
        })
        payload.changes.nodes_removed?.forEach((nodeId) => {
          eventBus.emit('NodeRemoved', { nodeId })
        })
        payload.changes.edges_added?.forEach((edge) => {
          eventBus.emit('EdgeAdded', { edge })
        })
        payload.changes.edges_removed?.forEach((edgeId) => {
          const [source, target] = edgeId.split(':')
          eventBus.emit('EdgeRemoved', { source: source || edgeId, target: target || '' })
        })
      } else if (isCognitiveEventPayload(payload)) {
        handleCognitiveEvent(payload)
      }
    }

    this.eventSource.onerror = () => {
      if (!this.url || this.manuallyDisconnected) return

      eventBus.emit('SSEDisconnected', undefined)
      this.eventSource?.close()
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect() {
    if (!this.url || this.reconnectTimer !== null) return

    const delay = Math.min(1000 * 2 ** this.reconnectAttempt, 30000)
    this.reconnectAttempt += 1
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, delay)
  }
}

function isDeltaPayload(payload: unknown): payload is DeltaPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'type' in payload &&
    payload.type === 'delta' &&
    'seq' in payload &&
    'changes' in payload
  )
}

function isCognitiveEventPayload(payload: unknown): payload is CognitiveEventPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'type' in payload &&
    payload.type === 'cognitive_event' &&
    'event_type' in payload &&
    'data' in payload &&
    typeof (payload as CognitiveEventPayload).data === 'object'
  )
}

function handleCognitiveEvent(payload: CognitiveEventPayload) {
  const { event_type, data } = payload

  switch (event_type) {
    case 'activity_pulse':
      if (data.nodeId && data.intensity !== undefined) {
        eventBus.emit('AgentActivityPulse', {
          nodeId: data.nodeId,
          intensity: data.intensity,
          type: data.activity_type ?? 'recall',
        })
      }
      break

    case 'recall_burst':
      if (data.nodeIds && data.nodeIds.length > 0) {
        eventBus.emit('AgentRecallBurst', { nodeIds: data.nodeIds })
      }
      break

    case 'traversal_path':
      if (data.nodeIds && data.nodeIds.length > 0) {
        eventBus.emit('AgentTraversalPath', {
          nodeIds: data.nodeIds,
          edgeIds: data.edgeIds ?? [],
        })
      }
      break

    case 'golden_thread':
      if (data.nodeId && data.thread) {
        eventBus.emit('GoldenThreadReceived', {
          nodeId: data.nodeId,
          thread: data.thread,
        })
      }
      break
  }
}
