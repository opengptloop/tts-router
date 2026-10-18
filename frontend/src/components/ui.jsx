import { X } from 'lucide-react'

export function Spinner({ large = false }) {
  return <span className={large ? 'spinner lg' : 'spinner'} aria-label="loading" />
}

export function Progress({ value, indeterminate = false }) {
  const pct = Math.max(0, Math.min(1, value || 0)) * 100
  return (
    <div className={indeterminate ? 'progress indeterminate' : 'progress'}>
      <span style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Badge({ tone = 'neutral', children, style }) {
  return (
    <span className={`badge ${tone}`} style={style}>
      {children}
    </span>
  )
}

export function Field({ label, help, children }) {
  return (
    <div className="field">
      {label && <label>{label}</label>}
      {children}
      {help && <span className="help">{help}</span>}
    </div>
  )
}

export function Modal({ title, onClose, children, width }) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className="modal" style={width ? { maxWidth: width } : undefined}>
        <div className="row between" style={{ marginBottom: 12 }}>
          <h2>{title}</h2>
          <button className="btn ghost icon" onClick={onClose} aria-label="Close">
            <X size={17} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function StatTile({ label, value, percent, detail }) {
  return (
    <div className="stat-tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {detail && <div className="small muted">{detail}</div>}
      {percent !== undefined && (
        <div className="bar">
          <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
        </div>
      )}
    </div>
  )
}

// Render an engine option spec (from the backend) as an input control.
export function OptionControl({ spec, value, onChange }) {
  const current = value ?? spec.default
  if (spec.type === 'bool') {
    return (
      <label className="toggle-row" style={{ marginBottom: 12 }}>
        <input
          type="checkbox"
          checked={Boolean(current)}
          onChange={(e) => onChange(spec.key, e.target.checked)}
        />
        <span>
          {spec.label}
          {spec.help ? <span className="help"> — {spec.help}</span> : null}
        </span>
      </label>
    )
  }
  if (spec.type === 'select') {
    return (
      <Field label={spec.label} help={spec.help}>
        <select
          className="select"
          value={current ?? ''}
          onChange={(e) => onChange(spec.key, e.target.value)}
        >
          {(spec.choices || []).map((choice) => (
            <option key={String(choice)} value={String(choice)}>
              {String(choice)}
            </option>
          ))}
        </select>
      </Field>
    )
  }
  const numeric = spec.type === 'float' || spec.type === 'int'
  return (
    <Field label={spec.label} help={spec.help}>
      <input
        className="input"
        type={numeric ? 'number' : 'text'}
        value={current ?? ''}
        min={spec.min ?? undefined}
        max={spec.max ?? undefined}
        step={spec.step ?? (spec.type === 'int' ? 1 : 'any')}
        placeholder={spec.default === null ? 'default' : undefined}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === '') return onChange(spec.key, null)
          onChange(spec.key, numeric ? Number(raw) : raw)
        }}
      />
    </Field>
  )
}

export function OptionList({ specs, values, onChange, advanced = false }) {
  const list = (specs || []).filter((spec) => Boolean(spec.advanced) === advanced)
  if (!list.length) return null
  return (
    <>
      {list.map((spec) => (
        <OptionControl
          key={spec.key}
          spec={spec}
          value={values?.[spec.key]}
          onChange={onChange}
        />
      ))}
    </>
  )
}
