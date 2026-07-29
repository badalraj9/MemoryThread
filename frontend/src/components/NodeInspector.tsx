import { AnimatePresence, motion } from 'framer-motion'
import { GitBranch, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { getGoldenThread } from '../api/client'
import { eventBus } from '../event-bus/EventBus'
import { useGraphStore } from '../store/graph-store'
import type { GoldenThreadNode, TruthVector } from '../types/graph'

const truthLabels: Array<[keyof TruthVector, string]> = [
  ['confidence', 'Confidence'],
  ['authority', 'Authority'],
  ['freshness', 'Freshness'],
  ['corroboration', 'Corroboration'],
]

export default function NodeInspector() {
  const selectedNodeId = useGraphStore((state) => state.selectedNodeId)
  const nodes = useGraphStore((state) => state.nodes)
  const edges = useGraphStore((state) => state.edges)
  const [thread, setThread] = useState<GoldenThreadNode[]>([])

  const node = useMemo(
    () => nodes.find((candidate) => candidate.id === selectedNodeId),
    [nodes, selectedNodeId],
  )

  const related = useMemo(() => {
    if (!node) return []
    const neighborIds = new Set(
      edges
        .filter((edge) => edge.source === node.id || edge.target === node.id)
        .flatMap((edge) => [edge.source, edge.target])
        .filter((id) => id !== node.id),
    )

    return nodes.filter((candidate) => neighborIds.has(candidate.id)).slice(0, 5)
  }, [edges, node, nodes])

  useEffect(() => {
    if (!node) {
      setThread([])
      return
    }

    let cancelled = false
    eventBus.emit('GoldenThreadRequested', { nodeId: node.id })

    getGoldenThread(node.id).then((nextThread) => {
      if (cancelled) return
      setThread(nextThread)
      eventBus.emit('GoldenThreadReceived', { nodeId: node.id, thread: nextThread })
    })

    return () => {
      cancelled = true
    }
  }, [node])

  const close = () => eventBus.emit('InspectorClosed', undefined)

  return (
    <AnimatePresence>
      {node ? (
        <motion.aside
          className="absolute right-5 top-24 z-20 flex max-h-[calc(100dvh-128px)] w-[min(390px,calc(100vw-32px))] flex-col overflow-hidden border border-white/10 bg-[#050607]/85 text-[#d6d9df] shadow-[0_0_80px_rgba(0,0,0,0.65)] backdrop-blur-xl"
          initial={{ opacity: 0, x: 42 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 42 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
        >
          <header className="flex items-start gap-4 border-b border-white/10 px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#00f3ff]">
                {node.type}
              </p>
              <h2 className="mt-2 text-xl font-light leading-tight text-white">
                {node.label}
              </h2>
            </div>
            <button
              aria-label="Close inspector"
              className="grid h-8 w-8 shrink-0 place-items-center text-[#4a505a] transition hover:text-white"
              type="button"
              onClick={close}
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="min-h-0 overflow-y-auto px-5 py-5">
            <p className="text-sm leading-6 text-[#7a828e]">{node.content}</p>

            <section className="mt-7">
              <div className="flex items-center justify-between">
                <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-white/80">
                  4D Truth Vector
                </h3>
                <span className="font-mono text-xs text-[#ffaa00]">
                  {Math.round(node.truth.composite * 100)}%
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {truthLabels.map(([key, label]) => (
                  <div key={key}>
                    <div className="mb-1 flex justify-between text-xs text-[#4a505a]">
                      <span>{label}</span>
                      <span>{Math.round(node.truth[key] * 100)}%</span>
                    </div>
                    <div className="h-1 overflow-hidden bg-white/10">
                      <div
                        className="h-full bg-gradient-to-r from-[#00f3ff] to-[#ffaa00]"
                        style={{ width: `${node.truth[key] * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="mt-8">
              <h3 className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-white/80">
                <GitBranch className="h-3.5 w-3.5 text-[#ffaa00]" />
                Golden Thread
              </h3>
              <div className="mt-4 space-y-3">
                {thread.map((item, idx) => (
                  <div key={`${item.timestamp}-${idx}`} className="border-l border-[#ffaa00]/40 pl-4">
                    <p className="text-sm text-white">{item.action}</p>
                    <p className="mt-1 font-mono text-[11px] text-[#4a505a]">
                      {item.actor} / {new Date(item.timestamp).toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            <section className="mt-8">
              <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-white/80">
                Related Memories
              </h3>
              <div className="mt-4 space-y-2">
                {related.map((relatedNode) => (
                  <button
                    key={relatedNode.id}
                    className="block w-full border border-white/10 px-3 py-3 text-left text-sm text-[#7a828e] transition hover:border-[#00f3ff]/50 hover:text-white"
                    type="button"
                    onClick={() => eventBus.emit('NodeSelected', { nodeId: relatedNode.id })}
                  >
                    {relatedNode.label}
                  </button>
                ))}
              </div>
            </section>
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}
