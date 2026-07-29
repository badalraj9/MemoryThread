import * as THREE from 'three'
import type { GraphEdge, GraphNode } from '../types/graph'

export class SynapticFilamentRenderer {
  private group: THREE.Group
  private lineGeometry: THREE.BufferGeometry
  private lineMaterial: THREE.LineBasicMaterial
  private linesMesh: THREE.LineSegments

  constructor() {
    this.group = new THREE.Group()
    this.lineGeometry = new THREE.BufferGeometry()

    this.lineMaterial = new THREE.LineBasicMaterial({
      color: 0x00f3ff,
      transparent: true,
      opacity: 0.25,
      blending: THREE.AdditiveBlending,
    })

    this.linesMesh = new THREE.LineSegments(this.lineGeometry, this.lineMaterial)
    this.group.add(this.linesMesh)
  }

  public getMesh(): THREE.Group {
    return this.group
  }

  /**
   * Updates 3D synaptic filaments between connected node centers.
   * Uses smooth 3D Catmull-Rom spline curves threading inside the volumetric cloud.
   */
  public updateFilaments(nodes: GraphNode[], edges: GraphEdge[]): void {
    if (nodes.length === 0 || edges.length === 0) {
      this.lineGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3))
      return
    }

    const nodeMap = new Map<string, GraphNode>()
    for (const node of nodes) {
      if (node.x !== undefined && node.y !== undefined && node.z !== undefined) {
        nodeMap.set(node.id, node)
      }
    }

    const points: number[] = []
    const curvePointsCount = 12

    for (const edge of edges) {
      const source = nodeMap.get(edge.source)
      const target = nodeMap.get(edge.target)
      if (!source || !target) continue

      const p1 = new THREE.Vector3(source.x, source.y, source.z)
      const p2 = new THREE.Vector3(target.x, target.y, target.z)

      // Control points for smooth organic curve
      const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5)
      const dist = p1.distanceTo(p2)
      const perpOffset = new THREE.Vector3(
        Math.sin(source.x! + target.y!) * dist * 0.15,
        Math.cos(source.y! + target.z!) * dist * 0.15,
        Math.sin(source.z! + target.x!) * dist * 0.15,
      )
      const controlPoint = mid.add(perpOffset)

      const curve = new THREE.QuadraticBezierCurve3(p1, controlPoint, p2)
      const curvePts = curve.getPoints(curvePointsCount)

      for (let i = 0; i < curvePts.length - 1; i += 1) {
        const ptA = curvePts[i]
        const ptB = curvePts[i + 1]
        points.push(ptA.x, ptA.y, ptA.z, ptB.x, ptB.y, ptB.z)
      }
    }

    const floatArray = new Float32Array(points)
    this.lineGeometry.setAttribute('position', new THREE.BufferAttribute(floatArray, 3))
    this.lineGeometry.computeBoundingSphere()
  }

  public dispose(): void {
    this.lineGeometry.dispose()
    this.lineMaterial.dispose()
  }
}
