import { useEffect, useRef } from 'react'
import { CognitiveFieldEngine } from '../../engine/CognitiveFieldEngine'

export default function CognitiveCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const engine = new CognitiveFieldEngine(container)
    engine.resize()
    engine.start()

    const handleResize = () => engine.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      engine.dispose()
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 z-0 cursor-crosshair bg-[#050607]"
      aria-label="Cognitive field"
    />
  )
}
