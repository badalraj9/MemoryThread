import * as THREE from 'three'
import { eventBus } from '../event-bus/EventBus'
import { useGraphStore } from '../store/graph-store'
import { ActivationEngine } from './ActivationEngine'
import { CameraController } from './CameraController'
import { DataTexture3DManager } from './DataTexture3DManager'
import { ForceSimulation } from './ForceSimulation'
import { SelectionManager } from './SelectionManager'
import { SynapticFilamentRenderer } from './SynapticFilamentRenderer'
import { VolumetricFieldRenderer } from './VolumetricFieldRenderer'

export class CognitiveFieldEngine {
  private container: HTMLElement
  private renderer: THREE.WebGLRenderer
  private scene: THREE.Scene
  private cameraController: CameraController

  private textureManager: DataTexture3DManager
  private fieldRenderer: VolumetricFieldRenderer
  private filamentRenderer: SynapticFilamentRenderer
  private forceSimulation: ForceSimulation
  private activationEngine: ActivationEngine
  private selectionManager: SelectionManager

  private animationFrameId: number = 0
  private clock: THREE.Clock
  private unsubscribeStore: () => void

  constructor(container: HTMLElement) {
    this.container = container
    this.scene = new THREE.Scene()
    this.clock = new THREE.Clock()

    // 1. WebGL Renderer Initialization
    const width = container.clientWidth || window.innerWidth
    const height = container.clientHeight || window.innerHeight

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    this.renderer.setSize(width, height)
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    container.appendChild(this.renderer.domElement)

    // 2. Camera Controller
    this.cameraController = new CameraController(width / height)
    this.cameraController.attachListeners(container)

    // 3. Volumetric Engine Modules
    this.textureManager = new DataTexture3DManager()
    this.fieldRenderer = new VolumetricFieldRenderer(this.textureManager)
    this.filamentRenderer = new SynapticFilamentRenderer()
    this.forceSimulation = new ForceSimulation()
    this.activationEngine = new ActivationEngine()
    this.selectionManager = new SelectionManager()

    this.activationEngine.setFieldRenderer(this.fieldRenderer)

    // Add meshes to scene
    this.scene.add(this.fieldRenderer.getMesh())
    this.scene.add(this.filamentRenderer.getMesh())

    // Attach 3D Raycasting Selector
    this.selectionManager.attachListeners(container, this.cameraController.camera, () =>
      useGraphStore.getState().nodes,
    )

    // 4. Force Simulation Sync
    this.forceSimulation.onTick(() => {
      const { nodes, edges } = useGraphStore.getState()
      this.textureManager.updateNodes(nodes)
      this.filamentRenderer.updateFilaments(nodes, edges)
    })

    // 5. Subscribe to Zustand Store Changes
    this.unsubscribeStore = useGraphStore.subscribe((state) => {
      this.forceSimulation.setGraph(state.nodes, state.edges)
    })

    // 6. Listen to EventBus Catalog
    this.setupEventListeners()
  }

  private setupEventListeners(): void {
    eventBus.on('ActivationStarted', ({ seedIds }) => {
      const { nodes, edges } = useGraphStore.getState()
      this.activationEngine.triggerActivation(seedIds, nodes, edges)
    })

    eventBus.on('NodeSelected', ({ nodeId }) => {
      const node = useGraphStore.getState().nodes.find((n) => n.id === nodeId)
      if (node && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
        const pos = new THREE.Vector3(node.x, node.y, node.z)
        this.cameraController.focusOn(pos, 380)
        this.fieldRenderer.triggerRecallSurge(pos, node.truth?.confidence ?? 0.8)
      }
    })

    eventBus.on('CameraFocusRequested', ({ nodeIds }) => {
      const nodes = useGraphStore.getState().nodes.filter((n) => nodeIds.includes(n.id))
      if (nodes.length > 0) {
        const avg = new THREE.Vector3()
        let count = 0
        for (const n of nodes) {
          if (n.x !== undefined && n.y !== undefined && n.z !== undefined) {
            avg.add(new THREE.Vector3(n.x, n.y, n.z))
            count += 1
          }
        }
        if (count > 0) {
          avg.divideScalar(count)
          this.cameraController.focusOn(avg, Math.max(300, 500 - count * 20))
        }
      }
    })

    eventBus.on('CameraResetRequested', () => {
      this.cameraController.reset()
    })
  }

  public resize(): void {
    const width = this.container.clientWidth || window.innerWidth
    const height = this.container.clientHeight || window.innerHeight

    this.renderer.setSize(width, height)
    this.cameraController.resize(width / height)
  }

  public start(): void {
    const tick = () => {
      const elapsedTime = this.clock.getElapsedTime()

      // Update camera smooth movement
      this.cameraController.update()

      // Update Volumetric Field GLSL Uniforms
      this.fieldRenderer.update(elapsedTime, this.cameraController.camera)

      // Render Three.js Frame
      this.renderer.render(this.scene, this.cameraController.camera)

      this.animationFrameId = requestAnimationFrame(tick)
    }

    tick()
  }

  public dispose(): void {
    cancelAnimationFrame(this.animationFrameId)
    this.unsubscribeStore()

    this.forceSimulation.stop()
    this.textureManager.dispose()
    this.fieldRenderer.dispose()
    this.filamentRenderer.dispose()
    this.renderer.dispose()

    if (this.renderer.domElement.parentNode) {
      this.renderer.domElement.parentNode.removeChild(this.renderer.domElement)
    }
  }
}
