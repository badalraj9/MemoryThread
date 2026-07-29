import { create } from 'zustand'
import type { DeltaPayload, GraphEdge, GraphNode } from '../types/graph'

interface GraphState {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedNodeId: string | null
  hoveredNodeId: string | null
  searchQuery: string
  searchResults: string[]
  activatedNodeIds: string[]
  isSearching: boolean

  // Actions
  setNodes: (nodes: GraphNode[]) => void
  setEdges: (edges: GraphEdge[]) => void
  selectNode: (id: string | null) => void
  hoverNode: (id: string | null) => void
  setSearchQuery: (query: string) => void
  setSearchResults: (results: string[]) => void
  setActivatedNodeIds: (ids: string[]) => void
  setSearching: (searching: boolean) => void
  applyDelta: (delta: DeltaPayload) => void
  deselectNode: () => void
}

export const useGraphStore = create<GraphState>((set) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  hoveredNodeId: null,
  searchQuery: '',
  searchResults: [],
  activatedNodeIds: [],
  isSearching: false,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  selectNode: (id) => set({ selectedNodeId: id }),
  hoverNode: (id) => set({ hoveredNodeId: id }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSearchResults: (searchResults) => set({ searchResults }),
  setActivatedNodeIds: (activatedNodeIds) => set({ activatedNodeIds }),
  setSearching: (isSearching) => set({ isSearching }),
  deselectNode: () => set({ selectedNodeId: null }),

  applyDelta: (delta) =>
    set((state) => {
      const nextNodes = [...state.nodes]
      const nextEdges = [...state.edges]
      const { changes } = delta

      if (changes.nodes_removed?.length) {
        const removeSet = new Set(changes.nodes_removed)
        for (let i = nextNodes.length - 1; i >= 0; i--) {
          if (removeSet.has(nextNodes[i].id)) {
            nextNodes.splice(i, 1)
          }
        }
      }

      if (changes.nodes_updated?.length) {
        for (const update of changes.nodes_updated) {
          if (!update.id) continue
          const index = nextNodes.findIndex((n) => n.id === update.id)
          if (index !== -1) {
            nextNodes[index] = { ...nextNodes[index], ...update }
          }
        }
      }

      if (changes.nodes_added?.length) {
        for (const newObj of changes.nodes_added) {
          if (!nextNodes.some((n) => n.id === newObj.id)) {
            nextNodes.push(newObj)
          }
        }
      }

      if (changes.edges_removed?.length) {
        const removeEdgeSet = new Set(changes.edges_removed)
        for (let i = nextEdges.length - 1; i >= 0; i--) {
          const key = `${nextEdges[i].source}:${nextEdges[i].target}`
          if (removeEdgeSet.has(key) || removeEdgeSet.has(nextEdges[i].id)) {
            nextEdges.splice(i, 1)
          }
        }
      }

      if (changes.edges_added?.length) {
        for (const newEdge of changes.edges_added) {
          if (!nextEdges.some((e) => e.id === newEdge.id)) {
            nextEdges.push(newEdge)
          }
        }
      }

      return { nodes: nextNodes, edges: nextEdges }
    }),
}))
