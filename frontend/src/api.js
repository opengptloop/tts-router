// Thin API client. All requests go to the same origin: Vite proxies /api and
// /ws to the backend in dev, and a reverse proxy (or the backend itself when
// serving the built frontend) handles them in production.

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export async function api(path, options = {}) {
  const { method = 'GET', body, isForm = false, signal } = options
  const headers = {}
  let payload = body
  if (body !== undefined && !isForm) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(path, { method, headers, body: payload, signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError(
      'Cannot reach the backend. Is it running? (uvicorn on port 8000)',
      0,
      'network_error',
    )
  }
  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    throw new ApiError(
      typeof detail === 'string' && detail ? detail : `Request failed (${res.status})`,
      res.status,
      data && typeof data === 'object' ? data.code : undefined,
    )
  }
  return data
}

export const getJobs = (limit = 50) => api(`/api/jobs?limit=${limit}`)
export const getJob = (id) => api(`/api/jobs/${id}`)
export const cancelJob = (id) => api(`/api/jobs/${id}/cancel`, { method: 'POST' })

export async function waitForJob(jobId, { onUpdate, interval = 700, signal } = {}) {
  for (;;) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const job = await getJob(jobId)
    onUpdate?.(job)
    if (['succeeded', 'failed', 'cancelled'].includes(job.status)) return job
    await new Promise((resolve) => setTimeout(resolve, interval))
  }
}

export function connectLogStream(onRecord) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  let ws = null
  let closed = false
  let attempts = 0

  const open = () => {
    if (closed) return
    ws = new WebSocket(`${proto}://${window.location.host}/ws/logs`)
    ws.onopen = () => {
      attempts = 0
    }
    ws.onmessage = (event) => {
      try {
        onRecord(JSON.parse(event.data))
      } catch {
        /* ignore malformed frames */
      }
    }
    ws.onclose = () => {
      if (closed) return
      attempts += 1
      setTimeout(open, Math.min(8000, 500 * 2 ** attempts))
    }
  }
  open()
  return () => {
    closed = true
    try {
      ws?.close()
    } catch {
      /* noop */
    }
  }
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / 1024 ** index
  return `${value.toFixed(value >= 100 || index === 0 ? 0 : 1)} ${units[index]}`
}

export function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}

export function formatTime(unixSeconds) {
  if (!unixSeconds) return '—'
  return new Date(unixSeconds * 1000).toLocaleString()
}

export function estimateSeconds(text, speed = 1, charsPerSecond = 14) {
  const chars = (text || '').length
  if (!chars) return 0
  return chars / (charsPerSecond * Math.max(0.1, speed || 1))
}
