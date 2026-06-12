import { useAppStore, type Project, type ProviderConfig, type Character, type Term } from '../store'

// In desktop/packaged mode the frontend is served by the same FastAPI process,
// so API calls use same-origin relative paths ("/api/...").
// In dev mode the Vite proxy forwards "/api" to the backend.
// Advanced users can still point at a remote backend by setting a non-default
// host/port in Settings — only then do we emit an absolute URL.
const BASE_URL = () => {
  const { backendHost, backendPort } = useAppStore.getState()
  const isDefault =
    (backendHost === '127.0.0.1' || backendHost === 'localhost') && backendPort === 8000
  return isDefault ? '' : `http://${backendHost}:${backendPort}`
}

// Helper
async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(error || `HTTP ${response.status}`)
  }
  return response.json()
}

// Projects API
export const projectsApi = {
  list: () => fetchJson<{ projects: Project[] }>(`${BASE_URL()}/api/projects`),

  create: (data: { name: string; source_lang: string; target_lang: string }) =>
    fetchJson<Project>(`${BASE_URL()}/api/projects`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  get: (projectId: string) => fetchJson<Project>(`${BASE_URL()}/api/projects/${projectId}`),

  delete: (projectId: string) =>
    fetch(`${BASE_URL()}/api/projects/${projectId}`, { method: 'DELETE' }),
}

// Characters API
export const charactersApi = {
  list: (projectId: string) =>
    fetchJson<{ characters: Character[] }>(`${BASE_URL()}/api/projects/${projectId}/characters`),

  get: (projectId: string, characterId: string) =>
    fetchJson<Character>(`${BASE_URL()}/api/projects/${projectId}/characters/${characterId}`),

  save: (projectId: string, characterId: string, data: Record<string, unknown>) =>
    fetchJson<Character>(`${BASE_URL()}/api/projects/${projectId}/characters/${characterId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (projectId: string, characterId: string) =>
    fetch(`${BASE_URL()}/api/projects/${projectId}/characters/${characterId}`, {
      method: 'DELETE',
    }),
}

// Terms API
export const termsApi = {
  list: (projectId: string) =>
    fetchJson<{ terms: Term[] }>(`${BASE_URL()}/api/projects/${projectId}/terms`),

  get: (projectId: string, termId: string) =>
    fetchJson<Term>(`${BASE_URL()}/api/projects/${projectId}/terms/${encodeURIComponent(termId)}`),

  save: (projectId: string, termId: string, data: Record<string, unknown>) =>
    fetchJson<Term>(`${BASE_URL()}/api/projects/${projectId}/terms/${encodeURIComponent(termId)}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (projectId: string, termId: string) =>
    fetch(`${BASE_URL()}/api/projects/${projectId}/terms/${encodeURIComponent(termId)}`, {
      method: 'DELETE',
    }),
}

// Provider Config API
export const providerApi = {
  get: (projectId: string) =>
    fetchJson<ProviderConfig>(`${BASE_URL()}/api/projects/${projectId}/provider-config`),

  save: (projectId: string, config: ProviderConfig) =>
    fetchJson<ProviderConfig>(`${BASE_URL()}/api/projects/${projectId}/provider-config`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),
}

// Translation Reports API
export const reportsApi = {
  list: (projectId: string) =>
    fetchJson<{ reports: unknown[] }>(`${BASE_URL()}/api/projects/${projectId}/translation-reports`),

  get: (projectId: string, path: string) =>
    fetchJson<unknown>(`${BASE_URL()}/api/projects/${projectId}/translation-report?path=${encodeURIComponent(path)}`),
}

// Review API
export const reviewApi = {
  listItems: (projectId: string, reportPath: string) =>
    fetchJson<{ items: unknown[] }>(
      `${BASE_URL()}/api/projects/${projectId}/review-items?path=${encodeURIComponent(reportPath)}`
    ),

  decide: (projectId: string, data: {
    report_path: string
    item_id: string
    status: 'accept' | 'reject'
    rationale?: string
  }) =>
    fetchJson<unknown>(`${BASE_URL()}/api/projects/${projectId}/review-decisions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}

// Backend control
export const backendApi = {
  status: () => fetch(`${BASE_URL()}/api/health`, { method: 'GET' }).then(r => r.ok),

  start: async () => {
    const response = await fetch(`${BASE_URL()}/api/backend/start`, { method: 'POST' })
    return response.ok
  },

  stop: async () => {
    const response = await fetch(`${BASE_URL()}/api/backend/stop`, { method: 'POST' })
    return response.ok
  },
}

// Batch translation (new endpoints)
export const batchApi = {
  list: () => fetchJson<{ jobs: unknown[] }>(`${BASE_URL()}/api/batch/jobs`),

  create: (data: { input_path: string; output_path: string; config?: Record<string, unknown> }) =>
    fetchJson<unknown>(`${BASE_URL()}/api/batch/jobs`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  start: (jobId: string) =>
    fetch(`${BASE_URL()}/api/batch/jobs/${jobId}/start`, { method: 'POST' }),

  pause: (jobId: string) =>
    fetch(`${BASE_URL()}/api/batch/jobs/${jobId}/pause`, { method: 'POST' }),

  resume: (jobId: string) =>
    fetch(`${BASE_URL()}/api/batch/jobs/${jobId}/resume`, { method: 'POST' }),

  delete: (jobId: string) =>
    fetch(`${BASE_URL()}/api/batch/jobs/${jobId}`, { method: 'DELETE' }),

  status: (jobId: string) =>
    fetchJson<unknown>(`${BASE_URL()}/api/batch/jobs/${jobId}/status`),
}

// Translate (new endpoints for translation control)
export const translateApi = {
  start: async (projectId: string, inputPath: string, options?: {
    mode?: 'manga' | 'novel'
    format?: string
    parallel_mode?: string
    concurrency?: number
  }) => {
    const response = await fetch(`${BASE_URL()}/api/translate/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, input_path: inputPath, ...options }),
    })
    return response.json()
  },

  stop: async () => {
    const response = await fetch(`${BASE_URL()}/api/translate/stop`, { method: 'POST' })
    return response.ok
  },

  progress: async () => {
    const response = await fetch(`${BASE_URL()}/api/translate/progress`)
    return response.json()
  },

  status: async () => {
    const response = await fetch(`${BASE_URL()}/api/translate/status`)
    return response.json()
  },
}

// SSE for real-time progress
export function createProgressStream(onMessage: (data: unknown) => void) {
  const eventSource = new EventSource(`${BASE_URL()}/api/translate/progress/stream`)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch {
      onMessage(event.data)
    }
  }

  eventSource.onerror = () => {
    eventSource.close()
  }

  return () => eventSource.close()
}

// Translation engine (heavy ML deps installed on demand)
export interface EngineDependencyStatus {
  requirement: string
  label: string
  installed: boolean
}

export interface EngineStatus {
  ready: boolean
  dependencies: EngineDependencyStatus[]
  missing_count: number
  total_count: number
}

export const engineApi = {
  status: () => fetchJson<EngineStatus>(`${BASE_URL()}/api/engine/status`),
}

/**
 * Start an engine install and stream pip output.
 * Calls onLog for each line, onDone on success, onError on failure.
 * Returns a function that closes the stream.
 */
export function installEngineStream(handlers: {
  onLog: (line: string) => void
  onDone: () => void
  onError: () => void
}) {
  // EventSource only supports GET, so the SSE endpoint is reachable via GET too;
  // the backend route accepts the connection and streams pip output.
  const eventSource = new EventSource(`${BASE_URL()}/api/engine/install`)

  eventSource.addEventListener('log', (event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data)
      handlers.onLog(data.line ?? '')
    } catch {
      /* ignore malformed line */
    }
  })

  eventSource.addEventListener('done', () => {
    handlers.onDone()
    eventSource.close()
  })

  eventSource.addEventListener('error', () => {
    handlers.onError()
    eventSource.close()
  })

  return () => eventSource.close()
}