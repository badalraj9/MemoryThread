import { createFileRoute } from '@tanstack/react-router'
import MemorySpace from '../components/MemorySpace'

export const Route = createFileRoute('/explore')({
  component: MemorySpace,
})
