import { useCallback, useEffect, useState } from 'react'
import './App.css'

type HealthResponse = {
  status: string
  service: string
}

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000'
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, '')
const API_HEALTH_URL = new URL('/api/v1/health', `${API_BASE_URL}/`).toString()

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRetrying, setIsRetrying] = useState(false)

  const fetchHealthStatus = useCallback(async () => {
    setIsLoading(true)
    setIsRetrying(true)
    setError(null)

    try {
      const response = await fetch(API_HEALTH_URL, {
        headers: {
          Accept: 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const payload = (await response.json()) as HealthResponse
      setHealth(payload)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Backend unavailable'
      setError(message)
      setHealth(null)
    } finally {
      window.setTimeout(() => {
        setIsRetrying(false)
        setIsLoading(false)
      }, 150)
    }
  }, [])

  useEffect(() => {
    void fetchHealthStatus()
  }, [fetchHealthStatus])

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <span className={`status-badge ${error ? 'error' : 'ok'}`}>
          {error ? 'Offline' : health ? 'Online' : 'Checking backend'}
        </span>
        <h1>Document Intelligence API</h1>
        <p className="subtitle">
          A foundation for secure document intake, summarization, fine-print extraction,
          and grounded Q&amp;A workflows.
        </p>
        <ul className="feature-list">
          <li>Document upload and validation (planned)</li>
          <li>Summarization and legal analysis (planned)</li>
          <li>Fine-print extraction and findings review (planned)</li>
          <li>Cited Q&amp;A over document evidence (planned)</li>
        </ul>
      </section>

      <section className="status-panel" aria-live="polite">
        <h2>Connection status</h2>

        {isLoading && !error && !health && <p>Loading backend status...</p>}
        {isRetrying && <p>Retrying...</p>}

        {error ? (
          <div className="alert error-alert" role="alert">
            <span>Backend unavailable</span>
            <span>{error}</span>
          </div>
        ) : health ? (
          <div className="result success-result">
            <p>Status: {health.status}</p>
            <p>Service: {health.service}</p>
          </div>
        ) : null}

        <button type="button" onClick={() => void fetchHealthStatus()}>
          Retry
        </button>
      </section>
    </main>
  )
}

export default App
