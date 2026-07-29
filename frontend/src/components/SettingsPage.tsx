import { useEffect, useState } from 'react'

const DEFAULT_API_URL = 'http://localhost:8000'

export default function SettingsPage() {
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL)

  useEffect(() => {
    setApiUrl(localStorage.getItem('memorythread.apiUrl') ?? DEFAULT_API_URL)
  }, [])

  const handleApiUrlChange = (value: string) => {
    setApiUrl(value)
    localStorage.setItem('memorythread.apiUrl', value)
  }

  return (
    <main className="flex min-h-dvh w-screen items-center justify-center bg-[#050607] px-6 text-primary">
      <section className="w-full max-w-xl">
        <h1 className="text-3xl font-light tracking-wide">Settings</h1>
        <label className="mt-8 block text-sm text-secondary" htmlFor="api-url">
          API URL
        </label>
        <input
          id="api-url"
          className="mt-3 w-full border border-border-subtle bg-bg-surface px-4 py-3 font-mono text-sm text-primary outline-none transition focus:border-accent-primary"
          value={apiUrl}
          onChange={(event) => handleApiUrlChange(event.target.value)}
        />
      </section>
    </main>
  )
}
