import * as THREE from 'three'
import type { GraphNode } from '../types/graph'

export const GRID_SIZE = 64
const TOTAL_VOXELS = GRID_SIZE * GRID_SIZE * GRID_SIZE
const CHANNELS = 4 // RGBA

export class DataTexture3DManager {
  private data: Float32Array
  public texture: THREE.Data3DTexture
  private boundingRadius: number = 380

  constructor() {
    // Single pre-allocated float buffer
    this.data = new Float32Array(TOTAL_VOXELS * CHANNELS)

    this.texture = new THREE.Data3DTexture(
      this.data,
      GRID_SIZE,
      GRID_SIZE,
      GRID_SIZE,
    )
    this.texture.format = THREE.RGBAFormat
    this.texture.type = THREE.FloatType
    this.texture.minFilter = THREE.LinearFilter
    this.texture.magFilter = THREE.LinearFilter
    this.texture.wrapS = THREE.ClampToEdgeWrapping
    this.texture.wrapT = THREE.ClampToEdgeWrapping
    this.texture.wrapR = THREE.ClampToEdgeWrapping
    this.texture.needsUpdate = true
  }

  /**
   * Wyvill Quintic Kernel Voxel Density Rasterizer
   * Evaluates spatial density, authority, corroboration, and contradiction tearing.
   */
  public updateNodes(nodes: GraphNode[], contradictions: Array<[string, string]> = []): void {
    // Zero out grid without heap allocation
    this.data.fill(0)

    if (nodes.length === 0) {
      this.texture.needsUpdate = true
      return
    }

    const size = GRID_SIZE
    const invHalfRadius = 1.0 / this.boundingRadius
    const contradictionSet = new Set(contradictions.map(([a, b]) => `${a}:${b}`))

    // Compact voxel radius for tight, crisp neural cores
    const voxelRadius = 0.08 
    const radiusSq = voxelRadius * voxelRadius

    for (let index = 0; index < nodes.length; index += 1) {
      const node = nodes[index]
      if (node.x === undefined || node.y === undefined || node.z === undefined) continue

      // Map world position [-380, 380] to voxel UVW space [0, 1]
      const nx = (node.x * invHalfRadius + 1.0) * 0.5
      const ny = (node.y * invHalfRadius + 1.0) * 0.5
      const nz = (node.z * invHalfRadius + 1.0) * 0.5

      if (nx < 0.05 || nx > 0.95 || ny < 0.05 || ny > 0.95 || nz < 0.05 || nz > 0.95) continue

      const minX = Math.max(0, Math.floor((nx - voxelRadius) * size))
      const maxX = Math.min(size - 1, Math.ceil((nx + voxelRadius) * size))
      const minY = Math.max(0, Math.floor((ny - voxelRadius) * size))
      const maxY = Math.min(size - 1, Math.ceil((ny + voxelRadius) * size))
      const minZ = Math.max(0, Math.floor((nz - voxelRadius) * size))
      const maxZ = Math.min(size - 1, Math.ceil((nz + voxelRadius) * size))

      const confidence = node.truth?.confidence ?? 0.8
      const freshness = node.truth?.freshness ?? 0.8
      const authority = node.truth?.authority ?? 0.5
      const corroboration = node.truth?.corroboration ?? 0.5
      const peakWeight = confidence * freshness

      for (let z = minZ; z <= maxZ; z += 1) {
        const vz = (z + 0.5) / size
        const dz = vz - nz
        const dz2 = dz * dz

        for (let y = minY; y <= maxY; y += 1) {
          const vy = (y + 0.5) / size
          const dy = vy - ny
          const dy2 = dy * dy

          for (let x = minX; x <= maxX; x += 1) {
            const vx = (x + 0.5) / size
            const dx = vx - nx
            const dx2 = dx * dx

            const distSq = dx2 + dy2 + dz2
            if (distSq >= radiusSq) continue

            const r2 = distSq / radiusSq
            const r4 = r2 * r2
            const r6 = r4 * r2

            // Wyvill Quintic Kernel: (1 - 3*r^2 + 3*r^4 - r^6)
            const wyvill = 1.0 - 3.0 * r2 + 3.0 * r4 - r6
            const density = peakWeight * Math.max(0, wyvill)

            const voxelIndex = (z * size * size + y * size + x) * CHANNELS

            // Channel R: Additive Density (rho)
            this.data[voxelIndex] += density

            // Channel G: Weighted Authority (a)
            this.data[voxelIndex + 1] = Math.max(this.data[voxelIndex + 1], authority * density)

            // Channel B: Weighted Corroboration (k)
            this.data[voxelIndex + 2] = Math.max(this.data[voxelIndex + 2], corroboration * density)

            // Channel A: Contradiction Tear Flag
            for (let nextIndex = index + 1; nextIndex < nodes.length; nextIndex += 1) {
              const other = nodes[nextIndex]
              if (contradictionSet.has(`${node.id}:${other.id}`) || contradictionSet.has(`${other.id}:${node.id}`)) {
                this.data[voxelIndex + 3] = Math.min(1.0, this.data[voxelIndex + 3] + density * 0.8)
              }
            }
          }
        }
      }
    }

    this.texture.needsUpdate = true
  }

  public dispose(): void {
    this.texture.dispose()
  }
}
