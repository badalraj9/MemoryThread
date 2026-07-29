import * as THREE from 'three'

export class CameraController {
  public camera: THREE.PerspectiveCamera
  private target: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
  private currentTarget: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
  private radius: number = 650
  private targetRadius: number = 650
  private theta: number = 0
  private phi: number = Math.PI * 0.45
  private isDragging: boolean = false
  private previousMousePosition = { x: 0, y: 0 }

  constructor(aspect: number) {
    this.camera = new THREE.PerspectiveCamera(45, aspect, 1, 2000)
    this.updateCameraPosition()
  }

  public attachListeners(element: HTMLElement): void {
    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return
      this.isDragging = true
      this.previousMousePosition = { x: e.clientX, y: e.clientY }
    }

    const onMouseMove = (e: MouseEvent) => {
      if (!this.isDragging) return
      const deltaX = e.clientX - this.previousMousePosition.x
      const deltaY = e.clientY - this.previousMousePosition.y

      this.theta -= deltaX * 0.005
      this.phi = Math.max(0.1, Math.min(Math.PI - 0.1, this.phi - deltaY * 0.005))

      this.previousMousePosition = { x: e.clientX, y: e.clientY }
    }

    const onMouseUp = () => {
      this.isDragging = false
    }

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      this.targetRadius = Math.max(250, Math.min(1200, this.targetRadius + e.deltaY * 0.8))
    }

    element.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    element.addEventListener('wheel', onWheel, { passive: false })
  }

  public focusOn(position: THREE.Vector3, targetRadius: number = 450): void {
    this.target.copy(position)
    this.targetRadius = targetRadius
  }

  public reset(): void {
    this.target.set(0, 0, 0)
    this.targetRadius = 650
    this.theta = 0
    this.phi = Math.PI * 0.45
  }

  public update(): void {
    // Smooth lerp to target position & radius
    this.currentTarget.lerp(this.target, 0.08)
    this.radius += (this.targetRadius - this.radius) * 0.08

    this.updateCameraPosition()
  }

  private updateCameraPosition(): void {
    const x = this.currentTarget.x + this.radius * Math.sin(this.phi) * Math.sin(this.theta)
    const y = this.currentTarget.y + this.radius * Math.cos(this.phi)
    const z = this.currentTarget.z + this.radius * Math.sin(this.phi) * Math.cos(this.theta)

    this.camera.position.set(x, y, z)
    this.camera.lookAt(this.currentTarget)
  }

  public resize(aspect: number): void {
    this.camera.aspect = aspect
    this.camera.updateProjectionMatrix()
  }
}
