import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  AudioLines,
  Moon,
  ServerCog,
  Settings2,
  Sun,
  Terminal,
} from 'lucide-react'
import { api } from './api.js'
import { Toasts } from './components/Toasts.jsx'
import { StudioPage } from './pages/StudioPage.jsx'
import { ModelsPage } from './pages/ModelsPage.jsx'
import { LogsPage } from './pages/LogsPage.jsx'

export const AppContext = createContext(null)
export const useApp = () => useContext(AppContext)

const PAGES = {
  studio: { label: 'Studio', icon: AudioLines, title: 'Studio', subtitle: 'Generate speech with local models' },
  models: { label: 'Models & Config', icon: Settings2, title: 'Models & Config', subtitle: 'Install engines, manage voices and monitor the system' },
  logs: { label: 'Logs', icon: Terminal, title: 'Live Logs', subtitle: 'Streaming backend logs' },
}

export default function App() {
  const [page, setPage] = useState('studio')
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'dark')
  const [models, setModels] = useState(null)
  const [status, setStatus] = useState(null)
  const [online, setOnline] = useState(null)
  const [toasts, setToasts] = useState([])
  const toastSeq = useRef(0)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('tts-theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const update = useCallback((id, patch) => {
    setToasts((current) =>
      current.map((toast) => (toast.id === id ? { ...toast, ...patch } : toast)),
    )
  }, [])

  const push = useCallback(
    (toast) => {
      const id = ++toastSeq.current
      const entry = { id, type: 'info', duration: 6000, ...toast }
      setToasts((current) => [...current.slice(-4), entry])
      if (entry.duration > 0) {
        setTimeout(() => dismiss(id), entry.duration)
      }
      return id
    },
    [dismiss],
  )

  const refreshModels = useCallback(async () => {
    try {
      const data = await api('/api/models')
      setModels(data.engines)
      return data.engines
    } catch (error) {
      setOnline(false)
      throw error
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    try {
      const data = await api('/api/system/status')
      setStatus(data)
      setOnline(true)
      return data
    } catch {
      setOnline(false)
      return null
    }
  }, [])

  useEffect(() => {
    refreshModels().catch(() => {})
    refreshStatus()
    const interval = setInterval(refreshStatus, 5000)
    const slow = setInterval(() => refreshModels().catch(() => {}), 30000)
    return () => {
      clearInterval(interval)
      clearInterval(slow)
    }
  }, [refreshModels, refreshStatus])

  const value = useMemo(
    () => ({
      models,
      status,
      online,
      refreshModels,
      refreshStatus,
      push,
      update,
      dismiss,
      theme,
      setTheme,
      navigate: setPage,
    }),
    [models, status, online, refreshModels, refreshStatus, push, update, dismiss, theme],
  )

  const PageIcon = PAGES[page].icon

  return (
    <AppContext.Provider value={value}>
      <div className="app">
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-logo">
              <AudioLines size={18} />
            </span>
            <span>
              <div className="brand-name">TTS Studio</div>
              <div className="brand-sub">local · private · open source</div>
            </span>
          </div>

          {(Object.entries(PAGES) || []).map(([key, config]) => {
            const Icon = config.icon
            return (
              <button
                key={key}
                className={`nav-item ${page === key ? 'active' : ''}`}
                onClick={() => setPage(key)}
              >
                <Icon size={17} />
                {config.label}
              </button>
            )
          })}

          <div className="sidebar-footer">
            <div className="row" style={{ gap: 7 }}>
              <span
                className={`status-dot ${
                  online === null ? 'loading' : online ? 'online' : 'offline'
                }`}
              />
              <span>{online === null ? 'Connecting…' : online ? 'Backend online' : 'Backend offline'}</span>
            </div>
            {status && (
              <div>
                {status.app?.name} v{status.app?.version}
              </div>
            )}
          </div>
        </aside>

        <main className="main">
          <header className="topbar">
            <div>
              <h1 className="row" style={{ gap: 9 }}>
                <PageIcon size={19} style={{ color: 'var(--accent)' }} />
                {PAGES[page].title}
              </h1>
              <p className="subtitle">{PAGES[page].subtitle}</p>
            </div>
            <div className="topbar-actions">
              {status && (
                <span className="badge neutral mono" title="CPU / RAM usage">
                  <ServerCog size={12} /> CPU {Math.round(status.cpu.percent)}% · RAM{' '}
                  {Math.round(status.ram.percent)}%
                </span>
              )}
              <button
                className="btn ghost icon"
                title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              >
                {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
              </button>
            </div>
          </header>

          <div className="content">
            {page === 'studio' && <StudioPage />}
            {page === 'models' && <ModelsPage />}
            {page === 'logs' && <LogsPage />}
          </div>
        </main>
      </div>
      <Toasts toasts={toasts} dismiss={dismiss} />
    </AppContext.Provider>
  )
}
