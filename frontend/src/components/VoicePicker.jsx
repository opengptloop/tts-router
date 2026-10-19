import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BadgeCheck,
  Check,
  ChevronDown,
  Download,
  Lock,
  Play,
  Search,
  User,
} from 'lucide-react'
import { Spinner } from './ui.jsx'
import { formatBytes } from '../api.js'

function matches(voice, query) {
  if (!query) return true
  const haystack = [
    voice.id,
    voice.name,
    voice.description,
    voice.language,
    voice.extra?.qualities,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return query
    .toLowerCase()
    .split(/\s+/)
    .every((term) => haystack.includes(term))
}

export function VoicePicker({
  voices = [],
  value,
  onChange,
  onPreview,
  previewingId,
  onDownload,
  downloading,
  withPreview = true,
  withQualityGroups = false,
  placeholder = 'Select a voice…',
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [gender, setGender] = useState('all')
  const [language, setLanguage] = useState('all')
  const [quality, setQuality] = useState('all')
  const [downloadedOnly, setDownloadedOnly] = useState(false)
  const rootRef = useRef(null)

  const selected = voices.find((voice) => voice.id === value)

  useEffect(() => {
    if (!open) return undefined
    const onDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false)
    }
    const onKey = (event) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const languages = useMemo(
    () => [...new Set(voices.map((voice) => voice.language).filter(Boolean))].sort(),
    [voices],
  )
  const qualities = useMemo(
    () =>
      [
        ...new Set(
          voices.map((voice) => voice.extra?.quality).filter((q) => q && q !== 'custom'),
        ),
      ].sort(),
    [voices],
  )
  const hasGenders = useMemo(() => voices.some((voice) => voice.gender), [voices])
  const hasDownloads = useMemo(
    () => voices.some((voice) => voice.downloaded === false),
    [voices],
  )

  const filtered = useMemo(
    () =>
      voices.filter(
        (voice) =>
          matches(voice, query) &&
          (gender === 'all' || voice.gender === gender) &&
          (language === 'all' || voice.language === language) &&
          (quality === 'all' || voice.extra?.quality === quality) &&
          (!downloadedOnly || voice.downloaded !== false),
      ),
    [voices, query, gender, language, quality, downloadedOnly],
  )

  const groups = useMemo(() => {
    const map = new Map()
    for (const voice of filtered) {
      const key = voice.language || 'Other'
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(voice)
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [filtered])

  const pick = (voice) => {
    if (voice.downloaded === false) return
    onChange(voice)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="voice-picker" ref={rootRef}>
      <button
        type="button"
        className={`voice-picker-trigger ${open ? 'open' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
      >
        {selected ? (
          <span className="row" style={{ minWidth: 0 }}>
            <span>{selected.extra?.flag || '🎙️'}</span>
            <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {selected.name}
            </span>
            {selected.gender && (
              <span className="muted small">{selected.gender === 'female' ? '♀' : '♂'}</span>
            )}
            {selected.downloaded === false && <Lock size={12} className="muted" />}
          </span>
        ) : (
          <span className="muted">{placeholder}</span>
        )}
        <ChevronDown size={16} className="muted" />
      </button>

      {open && (
        <div className="voice-menu">
          <div className="search">
            <div className="row" style={{ marginBottom: 8 }}>
              <Search size={15} className="muted" />
              <input
                className="input"
                style={{ padding: '7px 10px' }}
                placeholder={`Search ${voices.length} voices…`}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoFocus
              />
            </div>
            <div className="row wrap small">
              {hasGenders && (
                <div className="row" style={{ gap: 4 }}>
                  {[
                    ['all', 'All'],
                    ['female', '♀ F'],
                    ['male', '♂ M'],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      className={`btn sm ${gender === key ? 'primary' : 'ghost'}`}
                      onClick={() => setGender(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              {languages.length > 1 && (
                <select
                  className="select"
                  style={{ width: 'auto', padding: '5px 28px 5px 9px', fontSize: 12 }}
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="all">All languages</option>
                  {languages.map((lang) => (
                    <option key={lang} value={lang}>
                      {lang}
                    </option>
                  ))}
                </select>
              )}
              {withQualityGroups && qualities.length > 1 && (
                <select
                  className="select"
                  style={{ width: 'auto', padding: '5px 28px 5px 9px', fontSize: 12 }}
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                >
                  <option value="all">All qualities</option>
                  {qualities.map((q) => (
                    <option key={q} value={q}>
                      {q}
                    </option>
                  ))}
                </select>
              )}
              {hasDownloads && (
                <label className="toggle-row small">
                  <input
                    type="checkbox"
                    checked={downloadedOnly}
                    onChange={(e) => setDownloadedOnly(e.target.checked)}
                  />
                  Downloaded only
                </label>
              )}
            </div>
          </div>

          <div className="voice-list">
            {groups.length === 0 && <div className="voice-empty">No voices match.</div>}
            {groups.map(([groupName, groupVoices]) => (
              <div key={groupName}>
                <div className="voice-group-title">{groupName}</div>
                {groupVoices.map((voice) => {
                  const isSelected = voice.id === value
                  const unavailable = voice.downloaded === false
                  const isDownloading = Boolean(downloading?.[voice.id])
                  return (
                    <div
                      key={voice.id}
                      role="button"
                      tabIndex={0}
                      className={`voice-option ${isSelected ? 'selected' : ''} ${
                        unavailable ? 'disabled' : ''
                      }`}
                      onClick={() => pick(voice)}
                      onKeyDown={(e) => e.key === 'Enter' && pick(voice)}
                    >
                      <span style={{ width: 20, textAlign: 'center' }}>
                        {voice.extra?.flag || (voice.gender === 'female' ? '♀' : voice.gender === 'male' ? '♂' : '🎙️')}
                      </span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span className="name">
                          {voice.name}
                          {voice.custom && <span title="Custom voice">🧬</span>}
                          {voice.grade && (
                            <span className="badge neutral" style={{ padding: '1px 6px' }}>
                              {voice.grade}
                            </span>
                          )}
                          {voice.tags?.includes('cloning') && (
                            <span className="badge accent" style={{ padding: '1px 6px' }}>
                              clone
                            </span>
                          )}
                        </span>
                        <span className="desc">{voice.description || voice.id}</span>
                      </span>
                      <span className="row" style={{ gap: 4 }}>
                        {withQualityGroups && voice.extra?.quality && voice.extra.quality !== 'custom' && (
                          <span className="badge neutral" style={{ fontSize: 10.5 }}>
                            {voice.extra.quality}
                          </span>
                        )}
                        {voice.speaker_count > 1 && (
                          <span className="badge neutral" style={{ fontSize: 10.5 }}>
                            {voice.speaker_count} spk
                          </span>
                        )}
                        {voice.size_bytes ? (
                          <span className="muted small mono" style={{ fontSize: 10.5 }}>
                            {formatBytes(voice.size_bytes)}
                          </span>
                        ) : null}
                        {withPreview && onPreview && !unavailable && (
                          <button
                            type="button"
                            className="btn ghost icon sm"
                            title="Preview voice"
                            onClick={(e) => {
                              e.stopPropagation()
                              onPreview(voice)
                            }}
                          >
                            {previewingId === voice.id ? <Spinner /> : <Play size={13} />}
                          </button>
                        )}
                        {unavailable && onDownload && (
                          <button
                            type="button"
                            className="btn sm"
                            disabled={isDownloading}
                            title="Download this voice"
                            onClick={(e) => {
                              e.stopPropagation()
                              onDownload(voice)
                            }}
                          >
                            {isDownloading ? <Spinner /> : <Download size={13} />}
                            {isDownloading ? 'Downloading' : 'Download'}
                          </button>
                        )}
                        {!unavailable && voice.downloaded !== undefined && (
                          <BadgeCheck size={14} style={{ color: 'var(--success)' }} />
                        )}
                        {isSelected && <Check size={15} style={{ color: 'var(--accent)' }} />}
                        {voice.custom && <User size={13} className="muted" />}
                      </span>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
