import * as THREE from 'three'
import { eventBus } from '../event-bus/EventBus'
import type { GraphEdge, GraphNode } from '../types/graph'
import type { VolumetricFieldRenderer } from './VolumetricFieldRenderer'

export class ActivationEngine {
  private fieldRenderer: VolumetricFieldRenderer | null = null

  public setFieldRenderer(renderer: VolumetricFieldRenderer): void {
    this.fieldRenderer = renderer
  }

  /**
   * Triggers visual BFS propagation wave surges across memory edges.
   */
  public triggerActivation(seedIds: string[], nodes: GraphNode[], edges: GraphEdge[]): void {
    if (seedIds.length === 0 || !this.fieldRenderer) return

    const nodeMap = new Map<string, GraphNode>()
    for (const node of nodes) {
      nodeMap.set(node.id, node)
    }

    const adjacency = new Map<string, string[]>()
    for (const edge of edges) {
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, [])
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, [])
      adjacency.get(edge.source)!.push(edge.target)
      adjacency.get(edge.target)!.push(edge.source)
    }

    const visited = new Set<string>()
    const queue: Array<{ id: string; depth: number }> = seedIds.map((id) => ({ id, depth: 0 }))

    while (queue.length > 0) {
      const { id, depth } = queue.shift()!
      if (visited.has(id) || depth > 3) continue
      visited.add(id)

      const node = nodeMap.get(id)
      if (node && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
        const delay = depth * 120
        const pos = new THREE.Vector3(node.x, node.y, node.z)
        const confidence = node.truth?.confidence ?? 0.8

        window.setTimeout(() => {
          this.fieldRenderer?.triggerRecallSurge(pos, confidence)
          eventBus.emit('ActivationWave', { nodeId: id, intensity: 1.0 / (depth + 1), delayMs: delay })
        }, delay)
      }

      const neighbors = adjacency.get(id) ?? []
      for (const neighborId of neighbors) {
        if (!visited.has(neighborId)) {
          queue.push({ id: neighborId, depth: depth + 1 })
        }
      }
    }
  }
}
