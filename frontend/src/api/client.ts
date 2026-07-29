import type {
  GoldenThreadNode,
  GraphEdge,
  GraphNode,
  SearchResult,
  TruthVector,
} from '../types/graph'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const USE_MOCKS = import.meta.env.VITE_MOCK !== 'false'

const truth = (
  confidence: number,
  authority: number,
  freshness: number,
  corroboration: number,
): TruthVector => ({
  confidence,
  authority,
  freshness,
  corroboration,
  composite: Number(
    ((confidence + authority + freshness + corroboration) / 4).toFixed(2),
  ),
})

const mockNodes: GraphNode[] = [
  ['n-01', 'User Identity', 'identity', 'User prefers concise engineering answers with concrete file references.', truth(0.93, 0.81, 0.88, 0.76)],
  ['n-02', 'MemoryThread Goal', 'decision', 'The product centers the cognitive graph as the primary interface.', truth(0.98, 0.92, 0.91, 0.84)],
  ['n-03', 'Green Accent', 'fact', 'The design system uses #3dd68c as the primary green accent.', truth(1, 0.95, 0.9, 0.9)],
  ['n-04', 'No Dashboard', 'preference', 'Permanent UI should avoid dashboards, sidebars, top bars, and chat surfaces.', truth(0.96, 0.89, 0.92, 0.82)],
  ['n-05', 'Truth Vector', 'workflow', 'Every memory node carries confidence, authority, freshness, corroboration, and composite truth dimensions.', truth(0.94, 0.86, 0.78, 0.8)],
  ['n-06', 'SSE Delta Stream', 'event', 'Graph changes arrive through server-sent delta payloads.', truth(0.82, 0.72, 0.88, 0.69)],
  ['n-07', 'Contradiction Model', 'belief', 'Contradictions should be surfaced rather than silently overwritten.', truth(0.89, 0.77, 0.68, 0.71)],
  ['n-08', 'Recall Search', 'workflow', 'Search activates nearby memories and returns ranked evidence snippets.', truth(0.84, 0.76, 0.83, 0.75)],
  ['n-09', 'Golden Thread', 'fact', 'The golden thread records provenance and mutation history for an entity.', truth(0.88, 0.84, 0.79, 0.73)],
  ['n-10', 'Failure Memory', 'failure', 'Earlier prototypes overused panels and diluted the graph-first interaction model.', truth(0.74, 0.61, 0.7, 0.58)],
  ['n-11', 'Model Upgrade', 'prediction', 'A future model migration will require re-evaluating confidence calibration.', truth(0.66, 0.54, 0.72, 0.49)],
  ['n-12', 'API Boundary', 'decision', 'The frontend reads graph state from REST and listens for live updates over SSE.', truth(0.9, 0.82, 0.86, 0.79)],
  ['n-13', 'Font Stack', 'fact', 'The interface uses Inter for UI copy and JetBrains Mono for technical metadata.', truth(0.98, 0.91, 0.87, 0.86)],
  ['n-14', 'Inspector Rule', 'preference', 'Inspectors are temporary overlays opened from direct graph interaction.', truth(0.91, 0.78, 0.9, 0.7)],
  ['n-15', 'Spatial Memory', 'belief', 'Meaning should emerge from distance, activation, and connection strength.', truth(0.81, 0.63, 0.8, 0.62)],
  ['n-16', 'Merge Flow', 'workflow', 'Similar memories can be merged after reviewing conflict and provenance data.', truth(0.72, 0.67, 0.69, 0.61)],
  ['n-17', 'Canvas Layer', 'decision', 'The explore route reserves the full viewport for a Three.js particle field.', truth(0.96, 0.87, 0.94, 0.8)],
  ['n-18', 'Freshness Drift', 'prediction', 'Low freshness memories should visually decay unless corroborated by later evidence.', truth(0.69, 0.59, 0.64, 0.56)],
  ['n-19', 'Backend Default', 'fact', 'The local backend default is http://localhost:8000.', truth(0.97, 0.88, 0.9, 0.83)],
  ['n-20', 'Activation Waves', 'event', 'Selecting a node triggers activation waves across high-confidence edges.', truth(0.78, 0.64, 0.82, 0.6)],
].map(([id, label, type, content, nodeTruth], index) => ({
  id,
  label,
  type,
  content,
  truth: nodeTruth,
  x: Math.cos(index) * 360,
  y: Math.sin(index) * 240,
})) as GraphNode[]

const mockEdges: GraphEdge[] = mockNodes.slice(1).map((node, index) => ({
  id: `e-${String(index + 1).padStart(2, '0')}`,
  source: mockNodes[index % 6].id,
  target: node.id,
  type: index % 3 === 0 ? 'supports' : index % 3 === 1 ? 'relates_to' : 'derives_from',
  confidence: Number((0.58 + (index % 7) * 0.05).toFixed(2)),
  weight: 1.0,
}))

function searchMockNodes(query: string): SearchResult[] {
  const normalizedQuery = query.toLowerCase().trim()
  if (!normalizedQuery) return []

  return mockNodes
    .map((node) => {
      const haystack = `${node.label} ${node.content} ${node.type}`.toLowerCase()
      const exactMatch = haystack.includes(normalizedQuery)
      const tokenHits = normalizedQuery
        .split(/\s+/)
        .filter((token) => haystack.includes(token)).length
      const score = exactMatch ? 0.96 : tokenHits > 0 ? 0.68 + tokenHits * 0.08 : 0

      return {
        nodeId: node.id,
        score: Number(Math.min(score, 0.98).toFixed(2)),
        content: node.content,
      }
    })
    .filter((result) => result.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 8)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export async function getGraph(): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  if (USE_MOCKS) {
    return { nodes: mockNodes, edges: mockEdges }
  }

  try {
    return await request('/graph')
  } catch {
    return { nodes: mockNodes, edges: mockEdges }
  }
}

export async function recallMemory(query: string): Promise<SearchResult[]> {
  if (USE_MOCKS) {
    return searchMockNodes(query)
  }

  try {
    return await request('/recall', {
      method: 'POST',
      body: JSON.stringify({ query }),
    })
  } catch {
    return searchMockNodes(query)
  }
}

export async function getGoldenThread(nodeId: string): Promise<GoldenThreadNode[]> {
  if (USE_MOCKS) {
    return [
      {
        nodeId,
        entityId: nodeId,
        action: 'created',
        actor: 'memory-ingest',
        timestamp: '2026-07-21T18:20:00.000Z',
      },
      {
        nodeId,
        entityId: nodeId,
        action: 'truth_vector_updated',
        actor: 'corroboration-worker',
        timestamp: '2026-07-22T09:45:00.000Z',
        delta: { confidence: 0.04, corroboration: 0.08 },
      },
    ]
  }

  try {
    return await request(`/golden-thread/${encodeURIComponent(nodeId)}`)
  } catch {
    return [
      {
        nodeId,
        entityId: nodeId,
        action: 'observed',
        actor: 'local-frontend',
        timestamp: new Date().toISOString(),
      },
    ]
  }
}

export async function forgetMemory(nodeId: string): Promise<void> {
  if (USE_MOCKS) {
    return
  }

  await request<void>(`/memory/${encodeURIComponent(nodeId)}`, {
    method: 'DELETE',
  })
}
