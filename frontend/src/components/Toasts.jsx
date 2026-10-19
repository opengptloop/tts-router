import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { Progress } from './ui.jsx'

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

export function Toasts({ toasts, dismiss }) {
  if (!toasts.length) return null
  return (
    <div className="toasts">
      {toasts.map((toast) => {
        const Icon = ICONS[toast.type] || Info
        return (
          <div key={toast.id} className={`toast ${toast.type}`}>
            <Icon size={17} style={{ marginTop: 1, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              {toast.title && <div className="title">{toast.title}</div>}
              {toast.body && <div className="body">{toast.body}</div>}
              {toast.progress !== undefined && toast.progress !== null && (
                <Progress value={toast.progress} indeterminate={toast.progress < 0} />
              )}
            </div>
            <button className="btn ghost icon" onClick={() => dismiss(toast.id)} aria-label="Dismiss">
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
