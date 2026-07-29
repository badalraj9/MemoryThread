import { useEffect } from 'react'
import { getGraph } from '../api/client'
import { eventBus } from '../event-bus/EventBus'
import { useGraphStore } from '../store/graph-store'
import CognitiveCanvas from './cognitive-field/CognitiveCanvas'
import NodeInspector from './NodeInspector'
import SearchOverlay from './SearchOverlay'

export default function MemorySpace() {
  const applyDelta = useGraphStore((state) => state.applyDelta)
  const deselectNode = useGraphStore((state) => state.deselectNode)
  const selectNode = useGraphStore((state) => state.selectNode)
  const setEdges = useGraphStore((state) => state.setEdges)
  const setNodes = useGraphStore((state) => state.setNodes)

  useEffect(() => {
    let cancelled = false

    getGraph().then((graph) => {
      if (cancelled) return
      setNodes(graph.nodes)
      setEdges(graph.edges)
    })

    return () => {
      cancelled = true
    }
  }, [setEdges, setNodes])

  useEffect(() => {
    const handleDelta = (payload: Parameters<typeof applyDelta>[0]) => applyDelta(payload)
    const handleSelection = ({ nodeId }: { nodeId: string }) => selectNode(nodeId)
    const handleInspectorClosed = () => deselectNode()

    eventBus.on('DeltaReceived', handleDelta)
    eventBus.on('NodeSelected', handleSelection)
    eventBus.on('InspectorClosed', handleInspectorClosed)

    return () => {
      eventBus.off('DeltaReceived', handleDelta)
      eventBus.off('NodeSelected', handleSelection)
      eventBus.off('InspectorClosed', handleInspectorClosed)
    }
  }, [applyDelta, deselectNode, selectNode])

  return (
    <main className="relative h-dvh w-screen overflow-hidden bg-[#050607] text-primary">
      <CognitiveCanvas />
      <SearchOverlay />
      <NodeInspector />
    </main>
  )
}
