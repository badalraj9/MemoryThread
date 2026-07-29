import * as THREE from 'three'
import type { DataTexture3DManager } from './DataTexture3DManager'
import { createVolumetricShaderMaterial, type VolumetricShaderUniforms } from './VolumetricRaymarchShader'

export class VolumetricFieldRenderer {
  private mesh: THREE.Mesh
  private material: THREE.ShaderMaterial
  private uniforms: VolumetricShaderUniforms
  private nextPulseSlot: number = 0

  constructor(textureManager: DataTexture3DManager) {
    // 3D Bounding Box Geometry scaling to bounding radius 800 ([-400, 400])
    const geometry = new THREE.BoxGeometry(800, 800, 800)
    this.material = createVolumetricShaderMaterial()
    this.uniforms = this.material.uniforms as unknown as VolumetricShaderUniforms

    this.uniforms.uVolumeTexture.value = textureManager.texture
    this.mesh = new THREE.Mesh(geometry, this.material)
  }

  public getMesh(): THREE.Mesh {
    return this.mesh
  }

  public update(time: number, _camera: THREE.Camera): void {
    this.uniforms.uTime.value = time

    // Keep inverse model matrix updated for local-space raymarching
    this.mesh.updateMatrixWorld()
    this.uniforms.modelMatrixInverse.value.copy(this.mesh.matrixWorld).invert()
  }

  /**
   * Triggers an analytical recall shockwave surge radiating from a memory position.
   */
  public triggerRecallSurge(position: THREE.Vector3, confidence: number = 0.8): void {
    const slot = this.nextPulseSlot
    this.nextPulseSlot = (this.nextPulseSlot + 1) % 8

    this.uniforms.uPulsePositions.value[slot].copy(position)
    this.uniforms.uPulseTimes.value[slot] = this.uniforms.uTime.value
    this.uniforms.uPulseVelocities.value[slot] = confidence * 4.0 + 1.0
  }

  public dispose(): void {
    this.mesh.geometry.dispose()
    this.material.dispose()
  }
}
