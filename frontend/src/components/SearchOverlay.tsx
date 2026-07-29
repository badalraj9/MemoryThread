import { RotateCcw, Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { recallMemory } from '../api/client'
import { eventBus } from '../event-bus/EventBus'
import { useGraphStore } from '../store/graph-store'

export default function SearchOverlay() {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  const isSearching = useGraphStore((state) => state.isSearching)
  const searchResults = useGraphStore((state) => state.searchResults)
  const nodes = useGraphStore((state) => state.nodes)
  const setActivatedNodeIds = useGraphStore((state) => state.setActivatedNodeIds)
  const setSearchQuery = useGraphStore((state) => state.setSearchQuery)
  const setSearchResults = useGraphStore((state) => state.setSearchResults)
  const setSearching = useGraphStore((state) => state.setSearching)

  // Keyboard shortcut listener ('/' to focus, 'Esc' to clear/blur)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== inputRef.current) {
        e.preventDefault()
        inputRef.current?.focus()
      } else if (e.key === 'Escape') {
        inputRef.current?.blur()
        if (value) {
          setValue('')
          eventBus.emit('NodeDeselected', undefined)
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [value])

  useEffect(() => {
    const query = value.trim()
    setSearchQuery(query)

    if (!query) {
      setSearching(false)
      setSearchResults([])
      setActivatedNodeIds([])
      return
    }

    setSearching(true)
    eventBus.emit('SearchStarted', { query })

    const timeout = window.setTimeout(() => {
      recallMemory(query)
        .then((results) => {
          const seedIds = results.map((result) => result.nodeId)
          setSearchResults(seedIds)
          setActivatedNodeIds(seedIds)
          eventBus.emit('SearchCompleted', { query, results })
          eventBus.emit('ActivationStarted', { seedIds })
          eventBus.emit('CameraFocusRequested', { nodeIds: seedIds, duration: 900 })
        })
        .finally(() => setSearching(false))
    }, 280)

    return () => window.clearTimeout(timeout)
  }, [setActivatedNodeIds, setSearchQuery, setSearchResults, setSearching, value])

  const clearSearch = () => {
    setValue('')
    eventBus.emit('NodeDeselected', undefined)
  }

  const resetCamera = () => {
    eventBus.emit('CameraResetRequested', undefined)
  }

  return (
    <div className="absolute left-1/2 top-6 z-10 flex w-[min(640px,calc(100vw-32px))] -translate-x-1/2 items-center gap-3 border border-white/10 bg-[#050607]/80 px-4 py-3 shadow-[0_0_60px_rgba(0,243,255,0.06)] backdrop-blur-xl">
      <span className="shrink-0 font-mono text-xs font-semibold tracking-[0.2em] text-[#00f3ff]">
        MEMORYTHREAD
      </span>
      <Search aria-hidden="true" className="h-4 w-4 shrink-0 text-[#00f3ff]/80" />
      <input
        ref={inputRef}
        className="min-w-0 flex-1 bg-transparent text-sm text-[#d6d9df] outline-none placeholder:text-[#4a505a]"
        placeholder="Search artificial mind... (Press '/')"
        aria-label="Search memory"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      {isSearching ? <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-[#00f3ff]" /> : null}

      {value ? (
        <button
          aria-label="Clear search"
          className="grid h-7 w-7 shrink-0 place-items-center text-[#4a505a] transition hover:text-white"
          type="button"
          onClick={clearSearch}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}

      <button
        aria-label="Reset camera"
        title="Reset camera view"
        className="grid h-7 w-7 shrink-0 place-items-center text-[#4a505a] transition hover:text-[#00f3ff]"
        type="button"
        onClick={resetCamera}
      >
        <RotateCcw className="h-3.5 w-3.5" />
      </button>

      {searchResults.length > 0 ? (
        <div className="pointer-events-none absolute left-0 top-[calc(100%+8px)] w-full border border-white/10 bg-[#050607]/85 px-4 py-3 text-xs text-[#7a828e] backdrop-blur-xl">
          <span className="font-mono text-[#00f3ff]">{searchResults.length}</span> memories activated
          <span className="ml-3 font-mono text-tertiary">
            {searchResults
              .slice(0, 3)
              .map((id) => nodes.find((node) => node.id === id)?.label)
              .filter(Boolean)
              .join(' / ')}
          </span>
        </div>
      ) : null}
    </div>
  )
}
