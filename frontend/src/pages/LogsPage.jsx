import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownToLine, Eraser, Pause, Play, Search, Terminal } from 'lucide-react'
import { api, connectLogStream } from '../api.js'
import { Badge, Spinner } from '../components/ui.jsx'

const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const LEVEL_RANK = Object.fromEntries(LEVELS.map((level, index) => [level, index]))
const MAX_RECORDS = 3000

export function LogsPage() {
  const [records, setRecords] = useState([])
  const [connected, setConnected] = useState(false)
  const [paused, setPaused] = useState(false)
  const [minLevel, setMinLevel] = useState('INFO')
  const [query, setQuery] = useState('')
  const [autoscroll, setAutoscroll] = useState(true)

  const lastSeqRef = useRef(0)
  const pausedRef = useRef(false)
  const viewRef = useRef(null)

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  const append = useCallback((incoming) => {
    const fresh = incoming.filter((record) => record.seq > lastSeqRef.current)
    if (!fresh.length) return
    lastSeqRef.current = fresh[fresh.length - 1].seq
    setRecords((current) => {
      const next = [...current, ...fresh]
      return next.length > MAX_RECORDS ? next.slice(next.length - MAX_RECORDS) : next
    })
  }, [])

  useEffect(() => {
    let disposed = false
    api('/api/logs?limit=800')
      .then((data) => {
        if (disposed) return
        append(data.items)
        setConnected(true)
      })
      .catch(() => setConnected(false))

    const disconnect = connectLogStream((record) => {
      setConnected(true)
      if (!pausedRef.current) append([record])
    })
    return () => {
      disposed = true
      disconnect()
    }
  }, [append])

  useEffect(() => {
    if (autoscroll && !paused && viewRef.current) {
      viewRef.current.scrollTop = viewRef.current.scrollHeight
    }
  }, [records, autoscroll, paused])

  const clearLogs = async () => {
    try {
      await api('/api/logs', { method: 'DELETE' })
      setRecords([])
      lastSeqRef.current = 0
    } catch {
      /* offline */
    }
  }

  const visible = useMemo(() => {
    const threshold = LEVEL_RANK[minLevel] ?? 0
    const needle = query.trim().toLowerCase()
    return records.filter((record) => {
      if ((LEVEL_RANK[record.level] ?? 0) < threshold) return false
      if (needle && !`${record.logger} ${record.message}`.toLowerCase().includes(needle)) return false
      return true
    })
  }, [records, minLevel, query])

  const errorCount = records.filter((record) => ['ERROR', 'CRITICAL'].includes(record.level)).length
  const warningCount = records.filter((record) => record.level === 'WARNING').length

  return (
    <div className="fade-in">
      <div className="card" style={{ marginTop: 0 }}>
        <div className="card-header">
          <div>
            <h2 className="card-title">
              <Terminal size={17} style={{ color: 'var(--accent)' }} /> Backend log stream
            </h2>
            <p className="card-subtitle">
              {connected ? 'WebSocket connected' : 'Connecting…'} · {records.length} buffered ·{' '}
              {warningCount} warnings · {errorCount} errors
            </p>
          </div>
          <span className="row" style={{ gap: 6 }}>
            {!connected && (
              <Badge tone="warning">
                <Spinner /> reconnecting
              </Badge>
            )}
            <button
              className={paused ? 'btn sm primary' : 'btn sm'}
              onClick={() => setPaused((value) => !value)}
            >
              {paused ? <Play size={13} /> : <Pause size={13} />}
              {paused ? 'Resume' : 'Pause'}
            </button>
            <button className="btn danger sm" onClick={clearLogs}>
              <Eraser size={13} /> Clear
            </button>
          </span>
        </div>

        <div className="row wrap" style={{ marginBottom: 12 }}>
          <div className="row" style={{ flex: 1, minWidth: 220, gap: 8 }}>
            <Search size={15} className="muted" />
            <input
              className="input"
              placeholder="Filter by text or logger…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={minLevel}
            onChange={(event) => setMinLevel(event.target.value)}
          >
            {LEVELS.map((level) => (
              <option key={level} value={level}>
                {level}+
              </option>
            ))}
          </select>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={autoscroll}
              onChange={(event) => setAutoscroll(event.target.checked)}
            />
            <ArrowDownToLine size={13} /> Autoscroll
          </label>
        </div>

        <div className="log-view" ref={viewRef}>
          {visible.length === 0 && (
            <div className="log-line">
              <span className="msg muted">
                No log records match the current filters. Generate speech or load a model to see
                activity.
              </span>
            </div>
          )}
          {visible.map((record) => (
            <div className="log-line" key={record.seq}>
              <span className="ts">{record.time}</span>
              <span className={`lvl ${record.level}`}>{record.level.slice(0, 4)}</span>
              <span className="src">{record.logger}</span>
              <span className="msg">{record.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
