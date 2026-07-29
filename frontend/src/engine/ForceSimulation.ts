import * as d3 from 'd3'
import type { GraphEdge, GraphNode } from '../types/graph'

export class ForceSimulation {
  private simulation: d3.Simulation<d3.SimulationNodeDatum, undefined>
  private nodes: GraphNode[] = []
  private edges: GraphEdge[] = []
  private onTickCallbacks: Array<() => void> = []

  constructor() {
    this.simulation = d3
      .forceSimulation<d3.SimulationNodeDatum>()
      .force('charge', d3.forceManyBody().strength(-280))
      .force('center', d3.forceCenter(0, 0))
      .force('collide', d3.forceCollide().radius(35))
      .alphaMin(0.001)

    this.simulation.on('tick', () => {
      // Synchronize 3D Z coordinates using angular displacement
      this.nodes.forEach((node, idx) => {
        if (node.z === undefined) {
          node.z = Math.sin(idx * 0.5) * 120
        }
      })

      for (const cb of this.onTickCallbacks) {
        cb()
      }
    })
  }

  public setGraph(nodes: GraphNode[], edges: GraphEdge[]): void {
    this.nodes = nodes
    this.edges = edges

    // Initialize 3D positions if missing
    this.nodes.forEach((node, i) => {
      if (node.x === undefined) node.x = (Math.random() - 0.5) * 300
      if (node.y === undefined) node.y = (Math.random() - 0.5) * 300
      if (node.z === undefined) node.z = Math.sin(i) * 150
    })

    const linkForce = d3
      .forceLink<d3.SimulationNodeDatum, d3.SimulationLinkDatum<d3.SimulationNodeDatum>>(
        this.edges.map((e) => ({ source: e.source, target: e.target })),
      )
      .id((d: d3.SimulationNodeDatum) => (d as GraphNode).id)
      .distance(90)

    this.simulation.nodes(this.nodes as d3.SimulationNodeDatum[])
    this.simulation.force('link', linkForce)
    this.simulation.alpha(0.4).restart()
  }

  public onTick(cb: () => void): void {
    this.onTickCallbacks.push(cb)
  }

  public stop(): void {
    this.simulation.stop()
  }
}
