import * as THREE from 'three'
import { eventBus } from '../event-bus/EventBus'
import type { GraphNode } from '../types/graph'

export class SelectionManager {
  private raycaster: THREE.Raycaster
  private mouse: THREE.Vector2

  constructor() {
    this.raycaster = new THREE.Raycaster()
    this.mouse = new THREE.Vector2(-100, -100)
  }

  public attachListeners(element: HTMLElement, camera: THREE.Camera, getNodes: () => GraphNode[]): void {
    const onClick = (e: MouseEvent) => {
      const rect = element.getBoundingClientRect()
      this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1

      this.raycaster.setFromCamera(this.mouse, camera)
      const nodes = getNodes()

      let closestNode: GraphNode | null = null
      let minDistance = Infinity

      for (const node of nodes) {
        if (node.x === undefined || node.y === undefined || node.z === undefined) continue
        const nodePos = new THREE.Vector3(node.x, node.y, node.z)

        // Calculate distance from ray to 3D node position
        const ray = this.raycaster.ray
        const dist = ray.distanceToPoint(nodePos)

        if (dist < 45 && dist < minDistance) {
          minDistance = dist
          closestNode = node
        }
      }

      if (closestNode) {
        eventBus.emit('NodeSelected', { nodeId: closestNode.id })
      } else {
        eventBus.emit('NodeDeselected', undefined)
      }
    }

    element.addEventListener('click', onClick)
  }
}
