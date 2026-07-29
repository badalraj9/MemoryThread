import { Link } from '@tanstack/react-router'
import { motion, type Variants } from 'framer-motion'
import { useEffect, useRef } from 'react'

type NeuralNode = {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  opacity: number
  pulseOffset: number
  activatedAt: number | null
}

const NODE_COUNT = 120
const CONNECTION_DISTANCE = 160
const ACTIVATION_DURATION = 1500

const statusVariants: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.28,
      delayChildren: 1.8,
    },
  },
}

const statusSegmentVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: [0, 0.85, 0.25, 0.7],
    transition: { duration: 0.7, ease: 'easeOut' },
  },
}

function createNode(width: number, height: number): NeuralNode {
  const angle = Math.random() * Math.PI * 2
  const speed = 0.04 + Math.random() * 0.11

  return {
    x: Math.random() * width,
    y: Math.random() * height,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    radius: 1.5 + Math.random() * 1.5,
    opacity: 0.15 + Math.random() * 0.25,
    pulseOffset: Math.random() * Math.PI * 2,
    activatedAt: null,
  }
}

export default function LandingPage() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const context = canvas.getContext('2d')
    if (!context) return

    let width = window.innerWidth
    let height = window.innerHeight
    let pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
    let animationFrame = 0
    let lastActivation = 0
    let nodes: NeuralNode[] = []

    const resize = () => {
      width = window.innerWidth
      height = window.innerHeight
      pixelRatio = Math.min(window.devicePixelRatio || 1, 2)

      canvas.width = Math.floor(width * pixelRatio)
      canvas.height = Math.floor(height * pixelRatio)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)

      nodes = Array.from({ length: NODE_COUNT }, () => createNode(width, height))
    }

    const activateNode = (now: number) => {
      const node = nodes[Math.floor(Math.random() * nodes.length)]
      if (node) {
        node.activatedAt = now
      }
    }

    const draw = (now: number) => {
      context.clearRect(0, 0, width, height)

      const glow = context.createRadialGradient(
        width * 0.5,
        height * 0.45,
        0,
        width * 0.5,
        height * 0.45,
        Math.max(width, height) * 0.72,
      )
      glow.addColorStop(0, 'rgba(61, 214, 140, 0.09)')
      glow.addColorStop(0.35, 'rgba(35, 112, 94, 0.035)')
      glow.addColorStop(1, 'rgba(5, 6, 7, 0)')
      context.fillStyle = glow
      context.fillRect(0, 0, width, height)

      if (now - lastActivation > 1000) {
        activateNode(now)
        lastActivation = now
      }

      for (const node of nodes) {
        node.x += node.vx
        node.y += node.vy

        if (node.x <= 0 || node.x >= width) node.vx *= -1
        if (node.y <= 0 || node.y >= height) node.vy *= -1

        node.x = Math.max(0, Math.min(width, node.x))
        node.y = Math.max(0, Math.min(height, node.y))
      }

      for (let index = 0; index < nodes.length; index += 1) {
        const node = nodes[index]

        for (let nextIndex = index + 1; nextIndex < nodes.length; nextIndex += 1) {
          const nextNode = nodes[nextIndex]
          const distance = Math.hypot(node.x - nextNode.x, node.y - nextNode.y)

          if (distance < CONNECTION_DISTANCE) {
            const closeness = 1 - distance / CONNECTION_DISTANCE
            const alpha = 0.03 + closeness * 0.05

            context.beginPath()
            context.moveTo(node.x, node.y)
            context.lineTo(nextNode.x, nextNode.y)
            context.strokeStyle = `rgba(255, 255, 255, ${alpha})`
            context.lineWidth = 0.25 + closeness * 0.8
            context.stroke()
          }
        }
      }

      for (const node of nodes) {
        const pulse = (Math.sin(now * 0.0018 + node.pulseOffset) + 1) * 0.5
        const alpha = node.opacity * (0.7 + pulse * 0.45)

        context.beginPath()
        context.arc(node.x, node.y, node.radius + pulse * 0.45, 0, Math.PI * 2)
        context.fillStyle = `rgba(255, 255, 255, ${alpha})`
        context.fill()

        if (node.activatedAt !== null) {
          const elapsed = now - node.activatedAt

          if (elapsed > ACTIVATION_DURATION) {
            node.activatedAt = null
          } else {
            const progress = elapsed / ACTIVATION_DURATION
            const rippleRadius = 8 + progress * 92
            const rippleAlpha = (1 - progress) * 0.38

            context.beginPath()
            context.arc(node.x, node.y, node.radius + 4, 0, Math.PI * 2)
            context.fillStyle = 'rgba(61, 214, 140, 0.85)'
            context.shadowColor = '#3dd68c'
            context.shadowBlur = 22
            context.fill()
            context.shadowBlur = 0

            context.beginPath()
            context.arc(node.x, node.y, rippleRadius, 0, Math.PI * 2)
            context.strokeStyle = `rgba(61, 214, 140, ${rippleAlpha})`
            context.lineWidth = 1.2
            context.stroke()
          }
        }
      }

      animationFrame = window.requestAnimationFrame(draw)
    }

    resize()
    animationFrame = window.requestAnimationFrame(draw)
    window.addEventListener('resize', resize)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <main className="relative flex h-dvh min-h-screen w-screen items-center justify-center overflow-hidden bg-[#050607] px-6 text-white">
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="absolute inset-0 h-full w-full"
      />

      <section className="relative z-10 flex flex-col items-center text-center">
        <motion.p
          className="font-mono text-[11px] uppercase tracking-[0.3em] text-[#3dd68c]/70"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
        >
          Cognitive Memory Engine
        </motion.p>

        <motion.h1
          className="mt-5 font-sans text-[clamp(3rem,8vw,5.5rem)] font-extralight leading-none tracking-[-0.02em] text-white"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
        >
          Memory Thread
        </motion.h1>

        <motion.div
          aria-hidden="true"
          className="mt-7 h-px w-[200px] origin-center bg-gradient-to-r from-transparent via-[#3dd68c] to-transparent"
          initial={{ scaleX: 0, opacity: 0 }}
          animate={{ scaleX: 1, opacity: 1 }}
          transition={{ duration: 0.9, ease: 'easeOut', delay: 0.8 }}
        />

        <motion.p
          className="mt-7 font-sans text-base font-light text-[#7a828e]"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.85, ease: 'easeOut', delay: 1 }}
        >
          A truth-preserving cognitive graph for AI
        </motion.p>

        <motion.div
          className="mt-10 flex flex-col items-center gap-3 sm:flex-row"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: 'easeOut', delay: 1.4 }}
        >
          <Link
            to="/explore"
            className="inline-flex min-h-11 items-center justify-center border border-[#3dd68c] bg-transparent px-7 py-2.5 font-mono text-[13px] uppercase tracking-[0.08em] text-[#3dd68c] transition duration-200 hover:bg-[#3dd68c] hover:text-[#050607]"
          >
            Explore the Graph
          </Link>
          <a
            href="https://github.com/"
            className="inline-flex min-h-11 items-center justify-center border border-[#1a1f26] bg-transparent px-7 py-2.5 font-mono text-[13px] uppercase tracking-[0.08em] text-[#4a505a] transition duration-200 hover:border-[#3dd68c] hover:text-[#d6d9df]"
          >
            View on GitHub
          </a>
        </motion.div>
      </section>

      <motion.div
        className="absolute bottom-8 left-1/2 z-10 flex -translate-x-1/2 flex-wrap items-center justify-center gap-x-5 gap-y-2 px-6 text-center font-mono text-[11px] uppercase tracking-[0.18em] text-[#4a505a]"
        variants={statusVariants}
        initial="hidden"
        animate="visible"
        aria-label="System status"
      >
        {['System Ready', 'Graph Engine Online', 'SSE Stream Active'].map((segment) => (
          <motion.span key={segment} variants={statusSegmentVariants}>
            {segment}
          </motion.span>
        ))}
      </motion.div>
    </main>
  )
}
