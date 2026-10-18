import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Download,
  Eraser,
  History,
  ListMusic,
  Pause,
  Play,
  Plus,
  Sparkles,
  Square,
  Trash2,
  Volume2,
} from 'lucide-react'
import { api, cancelJob, estimateSeconds, formatBytes, formatDuration, waitForJob } from '../api.js'
import { useApp } from '../App.jsx'
import { VoicePicker } from '../components/VoicePicker.jsx'
import { CustomVoiceModal } from '../components/CustomVoiceModal.jsx'
import { Badge, Field, OptionList, Progress, Spinner } from '../components/ui.jsx'

const DEFAULT_TEXT =
  'The quick brown fox jumps over the lazy dog. This audio was generated entirely on your own computer, with no cloud inference involved.'

export function StudioPage() {
  const { models, push, update, navigate } = useApp()
  const engines = models || []

  const [engineId, setEngineId] = useState(null)
  const [variantId, setVariantId] = useState(null)
  const [voices, setVoices] = useState([])
  const [voicesLoading, setVoicesLoading] = useState(false)
  const [voice, setVoice] = useState(null)
  const [speakerId, setSpeakerId] = useState(null)
  const [genOptions, setGenOptions] = useState({})
  const [text, setText] = useState(DEFAULT_TEXT)
  const [batchMode, setBatchMode] = useState(false)
  const [job, setJob] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [previewing, setPreviewing] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [downloading, setDownloading] = useState({})
  const [showCustomModal, setShowCustomModal] = useState(false)
  const activeJobRef = useRef(null)

  const engine = engines.find((item) => item.id === engineId) || null
  const variant = engine?.variants?.find((item) => item.id === variantId) || null
  const busy = job && ['queued', 'running'].includes(job.status)

  // ----- initial engine selection -------------------------------------
  useEffect(() => {
    if (engineId || !engines.length) return
    const saved = (() => {
      try {
        return localStorage.getItem('tts-engine')
      } catch {
        return null
      }
    })()
    const chosen =
      engines.find((item) => item.id === saved) ||
      engines.find((item) => item.installed) ||
      engines[0]
    setEngineId(chosen.id)
  }, [engines, engineId])

  // ----- variant defaults when engine changes --------------------------
  useEffect(() => {
    if (!engine) return
    setVariantId(engine.default_variant)
    try {
      localStorage.setItem('tts-engine', engine.id)
    } catch {
      /* ignore */
    }
  }, [engine])

  useEffect(() => {
    if (!variant) return
    const defaults = {}
    for (const spec of variant.gen_options || []) {
      if (spec.default !== null && spec.default !== undefined) defaults[spec.key] = spec.default
    }
    setGenOptions(defaults)
  }, [variant])

  // ----- voice loading --------------------------------------------------
  const loadVoices = useCallback(
    async (selectVoice = false) => {
      if (!engineId) return
      setVoicesLoading(true)
      try {
        const params = new URLSearchParams()
        if (variantId) params.set('variant', variantId)
        const data = await api(`/api/engines/${engineId}/voices?${params.toString()}`)
        setVoices(data.voices)
        setVoice((current) => {
          if (!selectVoice && current && data.voices.some((v) => v.id === current.id)) {
            return data.voices.find((v) => v.id === current.id)
          }
          if (engineId === 'piper') {
            const preferred =
              data.voices.find((v) => v.downloaded && v.id === 'en_US-lessac-medium') ||
              data.voices.find((v) => v.downloaded)
            if (preferred) return preferred
          }
          if (engineId === 'kokoro') {
            const heart = data.voices.find((v) => v.id === 'af_heart')
            if (heart) return heart
          }
          return data.voices.find((v) => v.downloaded !== false) || data.voices[0] || null
        })
      } catch (error) {
        push({ type: 'error', title: 'Could not load voices', body: error.message })
      } finally {
        setVoicesLoading(false)
      }
    },
    [engineId, variantId, push],
  )

  useEffect(() => {
    setVoice(null)
    setSpeakerId(null)
    if (engineId) loadVoices(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engineId, variantId])

  // ----- history ---------------------------------------------------------
  const loadHistory = useCallback(async () => {
    try {
      const data = await api('/api/history?limit=40')
      setHistory(data.items)
    } catch {
      /* backend offline */
    }
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // ----- actions ----------------------------------------------------------
  const runGeneration = async () => {
    if (!engine || !voice) return
    const clips = batchMode
      ? text.split(/\n+/).map((line) => line.trim()).filter(Boolean)
      : [text.trim()].filter(Boolean)
    if (!clips.length) {
      push({ type: 'warning', title: 'Nothing to generate', body: 'Type some text first.' })
      return
    }
    if (engine.installed === false) {
      push({
        type: 'warning',
        title: `${engine.name} is not installed`,
        body: 'Install it from the Models page first.',
      })
      return
    }

    setResult(null)
    let lastResult = null

    for (let index = 0; index < clips.length; index += 1) {
      const options = { ...genOptions }
      if (speakerId !== null && speakerId !== undefined) options.speaker_id = speakerId
      try {
        const { job_id } = await api('/api/generate', {
          method: 'POST',
          body: {
            engine: engine.id,
            model: variantId,
            voice: voice.id,
            text: clips[index],
            options,
          },
        })
        activeJobRef.current = job_id
        const finished = await waitForJob(job_id, {
          onUpdate: (snapshot) =>
            setJob({
              ...snapshot,
              clipLabel:
                clips.length > 1 ? `Clip ${index + 1} of ${clips.length}` : undefined,
            }),
        })
        activeJobRef.current = null
        setJob(finished)
        if (finished.status !== 'succeeded') {
          if (finished.status !== 'cancelled') {
            push({
              type: 'error',
              title: 'Generation failed',
              body: finished.error || 'Unknown error',
              duration: 12000,
            })
          }
          break
        }
        lastResult = finished.result
      } catch (error) {
        activeJobRef.current = null
        push({ type: 'error', title: 'Generation failed', body: error.message, duration: 12000 })
        break
      }
    }

    if (lastResult) {
      setResult(lastResult)
      push({
        type: 'success',
        title: 'Audio ready',
        body: `${formatDuration(lastResult.duration_s)} · ${lastResult.voice_label} · ${lastResult.sample_rate} Hz`,
      })
      loadHistory()
    }
    loadHistory()
  }

  const stopGeneration = async () => {
    if (activeJobRef.current) {
      try {
        await cancelJob(activeJobRef.current)
      } catch {
        /* already finished */
      }
    }
  }

  const previewVoice = async (target) => {
    setPreviewing(target.id)
    try {
      const { job_id } = await api('/api/voices/preview', {
        method: 'POST',
        body: { engine: engineId, model: variantId, voice: target.id },
      })
      const finished = await waitForJob(job_id)
      if (finished.status === 'succeeded') {
        setPreviewUrl(`${finished.result.audio_url}?t=${Date.now()}`)
      } else {
        push({ type: 'error', title: 'Preview failed', body: finished.error })
      }
    } catch (error) {
      push({ type: 'error', title: 'Preview failed', body: error.message })
    } finally {
      setPreviewing(null)
    }
  }

  const downloadVoice = async (target) => {
    setDownloading((current) => ({ ...current, [target.id]: 0.01 }))
    const toastId = push({
      type: 'info',
      title: `Downloading ${target.id}`,
      progress: 0,
      duration: 0,
    })
    try {
      const { job_id } = await api(`/api/engines/piper/voices/${target.id}/download`, {
        method: 'POST',
      })
      const finished = await waitForJob(job_id, {
        onUpdate: (snapshot) => {
          setDownloading((current) => ({ ...current, [target.id]: snapshot.progress }))
          update(toastId, { progress: snapshot.progress, body: snapshot.message })
        },
      })
      if (finished.status !== 'succeeded') throw new Error(finished.error || 'Download failed')
      update(toastId, {
        type: 'success',
        title: `Downloaded ${target.id}`,
        body: formatBytes(finished.result?.size_bytes),
        progress: null,
        duration: 4000,
      })
      await loadVoices()
    } catch (error) {
      update(toastId, {
        type: 'error',
        title: 'Download failed',
        body: error.message,
        progress: null,
        duration: 10000,
      })
    } finally {
      setDownloading((current) => {
        const next = { ...current }
        delete next[target.id]
        return next
      })
    }
  }

  const onCustomUploaded = async (uploaded) => {
    setShowCustomModal(false)
    push({ type: 'success', title: `Voice '${uploaded.name}' added` })
    await loadVoices()
    setVoice({
      id: `custom:${uploaded.id}`,
      name: uploaded.name,
      downloaded: true,
      custom: true,
      language: uploaded.language,
    })
  }

  // ----- derived ----------------------------------------------------------
  const chars = text.length
  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  const speed = Number(genOptions.speed ?? 1) || 1
  const charsPerSecond = engineId === 'pocket' ? 13 : engineId === 'piper' ? 15 : 14
  const estimated = estimateSeconds(text, speed, charsPerSecond)
  const clipCount = batchMode ? text.split(/\n+/).filter((line) => line.trim()).length : 1
  const selectedSpeakers = voice?.speakers || []

  const engineIcon = useMemo(() => {
    const map = { kokoro: '🌊', kitten: '🐱', pocket: '🎒', piper: '🎵' }
    return map[engineId] || '🎙️'
  }, [engineId])

  return (
    <div className="studio-layout fade-in">
      {/* ------------------------------ composer ------------------------ */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">
              <Sparkles size={17} style={{ color: 'var(--accent)' }} /> Compose
            </h2>
            <p className="card-subtitle">Everything runs on this machine</p>
          </div>
        </div>

        {engine && engine.installed === false && (
          <div
            className="row between"
            style={{
              gap: 10,
              padding: '10px 12px',
              marginBottom: 14,
              borderRadius: 10,
              background: 'var(--warning-soft)',
              border: '1px solid color-mix(in srgb, var(--warning) 40%, transparent)',
            }}
          >
            <span className="row small" style={{ color: 'var(--warning)' }}>
              <AlertTriangle size={15} /> {engine.name} is not installed yet.
            </span>
            <button className="btn sm" onClick={() => navigate('models')}>
              Install
            </button>
          </div>
        )}

        <div className="grid-2" style={{ gap: 12 }}>
          <Field label="Engine">
            <select
              className="select"
              value={engineId || ''}
              onChange={(event) => setEngineId(event.target.value)}
            >
              {engines.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                  {item.installed ? '' : ' (not installed)'}
                  {item.loaded ? ' · loaded' : ''}
                </option>
              ))}
            </select>
          </Field>

          {engine && engine.variants.length > 1 && (
            <Field label="Model variant">
              <select
                className="select"
                value={variantId || ''}
                onChange={(event) => setVariantId(event.target.value)}
              >
                {engine.variants.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>

        <Field label={`Voice ${voice ? `· ${voices.length} available` : ''}`}>
          <div className="row" style={{ alignItems: 'stretch' }}>
            <div style={{ flex: 1 }}>
              {voicesLoading ? (
                <div className="row muted small" style={{ padding: '10px 0' }}>
                  <Spinner /> Loading voices…
                </div>
              ) : (
                <VoicePicker
                  voices={voices}
                  value={voice?.id}
                  onChange={(next) => {
                    setVoice(next)
                    setSpeakerId(null)
                  }}
                  onPreview={previewVoice}
                  previewingId={previewing}
                  onDownload={engineId === 'piper' ? downloadVoice : undefined}
                  downloading={downloading}
                  withQualityGroups={engineId === 'piper'}
                />
              )}
            </div>
            <button
              className="btn"
              title="Add a custom voice"
              onClick={() => setShowCustomModal(true)}
              disabled={!engine}
            >
              <Plus size={15} /> Custom
            </button>
          </div>
        </Field>

        {selectedSpeakers.length > 0 && (
          <Field label="Speaker" help="This is a multi-speaker voice.">
            <select
              className="select"
              value={speakerId ?? ''}
              onChange={(event) =>
                setSpeakerId(event.target.value === '' ? null : Number(event.target.value))
              }
            >
              <option value="">Default speaker</option>
              {selectedSpeakers.map((speaker) => (
                <option key={speaker.id} value={speaker.id}>
                  {speaker.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        <Field label="Text">
          <textarea
            className="input"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={
              batchMode
                ? 'One clip per line — each line becomes its own audio file'
                : 'Type or paste the text to synthesize…'
            }
            rows={9}
          />
        </Field>

        <div className="row between wrap small muted" style={{ marginBottom: 12 }}>
          <span>
            {chars.toLocaleString()} chars · {words.toLocaleString()} words · ~
            {formatDuration(estimated)} audio
            {batchMode && clipCount > 1 ? ` · ${clipCount} clips` : ''}
          </span>
          <span className="row" style={{ gap: 8 }}>
            <label className="toggle-row small" title="Each line becomes its own clip">
              <input
                type="checkbox"
                checked={batchMode}
                onChange={(event) => setBatchMode(event.target.checked)}
              />
              Batch (one clip per line)
            </label>
            <button
              className="btn ghost sm"
              onClick={() => {
                setText('')
                setResult(null)
              }}
            >
              <Eraser size={13} /> Clear
            </button>
          </span>
        </div>

        {variant && (
          <>
            <OptionList
              specs={variant.gen_options}
              values={genOptions}
              onChange={(key, value) => setGenOptions((current) => ({ ...current, [key]: value }))}
            />
            {(variant.gen_options || []).some((spec) => spec.advanced) && (
              <details className="advanced">
                <summary>Advanced options</summary>
                <OptionList
                  advanced
                  specs={variant.gen_options}
                  values={genOptions}
                  onChange={(key, value) => setGenOptions((current) => ({ ...current, [key]: value }))}
                />
              </details>
            )}
          </>
        )}

        <div className="row" style={{ gap: 10 }}>
          <button
            className="btn primary lg"
            style={{ flex: 1 }}
            disabled={busy || !voice || engine?.installed === false}
            onClick={runGeneration}
          >
            {busy ? <Spinner /> : <Play size={17} />}
            {busy ? 'Generating…' : batchMode && clipCount > 1 ? `Generate ${clipCount} clips` : 'Generate'}
          </button>
          {busy && (
            <button className="btn danger" onClick={stopGeneration} title="Cancel">
              <Square size={15} /> Cancel
            </button>
          )}
        </div>

        {job && (busy || job.status === 'failed') && (
          <div style={{ marginTop: 14 }} className="fade-in">
            <div className="row between small" style={{ marginBottom: 6 }}>
              <span className="row" style={{ gap: 7, color: 'var(--text-soft)' }}>
                {job.clipLabel && <Badge tone="info">{job.clipLabel}</Badge>}
                {job.message || job.label}
              </span>
              <span className="muted">{Math.round((job.progress || 0) * 100)}%</span>
            </div>
            <Progress
              value={job.progress}
              indeterminate={job.progress === undefined || job.progress === null}
            />
            {job.status === 'failed' && (
              <p className="small" style={{ color: 'var(--danger)', marginBottom: 0 }}>
                {job.error}
              </p>
            )}
          </div>
        )}

        {result && (
          <div
            className="card fade-in audio-result"
            style={{ marginTop: 16, background: 'var(--panel-2)' }}
          >
            <div className="row between" style={{ marginBottom: 4 }}>
              <span className="row" style={{ gap: 8 }}>
                <Volume2 size={16} style={{ color: 'var(--success)' }} />
                <strong>Result</strong>
                <Badge tone="success">{formatDuration(result.duration_s)}</Badge>
                <Badge tone="neutral">{result.sample_rate} Hz</Badge>
                {result.wall_time_s ? (
                  <Badge tone="neutral">×{(result.duration_s / result.wall_time_s).toFixed(1)} realtime</Badge>
                ) : null}
              </span>
              <a className="btn sm" href={result.audio_url} download>
                <Download size={13} /> WAV
              </a>
            </div>
            <p className="small muted" style={{ margin: '2px 0 6px' }}>
              {result.engine_name || engine?.name} · {result.voice_label || voice?.name}
              {result.meta?.family ? ` · ${result.meta.family}` : ''}
            </p>
            <audio key={result.audio_url} controls autoPlay src={result.audio_url} />
          </div>
        )}
      </div>

      {/* ------------------------------ side ---------------------------- */}
      <div>
        {engine && (
          <div className="card">
            <div className="card-header" style={{ marginBottom: 10 }}>
              <div className="engine-card-head">
                <span className="engine-icon" style={{ fontSize: 18 }}>
                  {engineIcon}
                </span>
                <div>
                  <h3 className="card-title">{engine.name}</h3>
                  <p className="card-subtitle">
                    {variant?.label}
                    {engine.loaded ? ` · loaded on ${engine.device || 'cpu'}` : ''}
                  </p>
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                {engine.installed ? (
                  <Badge tone="success">installed</Badge>
                ) : (
                  <Badge tone="warning">not installed</Badge>
                )}
                {engine.loaded && <Badge tone="accent">loaded</Badge>}
              </div>
            </div>
            <p className="small muted" style={{ marginTop: 0 }}>
              {variant?.description || engine.description}
            </p>
            <div className="kv">
              <span className="k">License</span>
              <span className="v">{engine.license}</span>
            </div>
            <div className="kv">
              <span className="k">Download size</span>
              <span className="v">{variant?.size_hint || '—'}</span>
            </div>
            <div className="kv">
              <span className="k">Voice cloning</span>
              <span className="v">{engine.cloning ? 'supported' : 'not supported'}</span>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-header" style={{ marginBottom: 10 }}>
            <h3 className="card-title">
              <History size={16} /> Recent generations
            </h3>
            {history.length > 0 && (
              <button
                className="btn ghost sm"
                onClick={async () => {
                  await api('/api/history', { method: 'DELETE' })
                  loadHistory()
                }}
              >
                <Trash2 size={13} /> Clear
              </button>
            )}
          </div>
          {history.length === 0 && <p className="muted small">Nothing generated yet.</p>}
          {history.map((entry) => (
            <div key={entry.id} className="history-item">
              <button
                className="btn ghost icon"
                title="Load into player"
                onClick={() => setResult({ ...entry, engine_name: entry.engine })}
              >
                <Play size={14} />
              </button>
              <div className="meta">
                <div className="text">{entry.text || '(empty)'}</div>
                <div className="sub">
                  {entry.engine} · {entry.voice_label} · {formatDuration(entry.duration_s)} ·{' '}
                  {entry.created_at_iso}
                </div>
              </div>
              <a className="btn ghost icon" href={entry.audio_url} download title="Download">
                <Download size={14} />
              </a>
              <button
                className="btn ghost icon"
                title="Delete"
                onClick={async () => {
                  await api(`/api/history/${entry.id}`, { method: 'DELETE' })
                  loadHistory()
                }}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {previewUrl && (
        <div
          className="card"
          style={{
            position: 'fixed',
            bottom: 18,
            left: 18,
            width: 340,
            zIndex: 80,
            margin: 0,
          }}
        >
          <div className="row between" style={{ marginBottom: 6 }}>
            <span className="row small" style={{ gap: 7 }}>
              <ListMusic size={14} style={{ color: 'var(--accent)' }} /> Voice preview
            </span>
            <div className="row" style={{ gap: 6 }}>
              <button
                className="btn ghost icon"
                title="Stop"
                onClick={() => setPreviewUrl(null)}
              >
                <Pause size={13} />
              </button>
            </div>
          </div>
          <audio autoPlay controls src={previewUrl} style={{ width: '100%' }} />
        </div>
      )}

      {showCustomModal && engine && (
        <CustomVoiceModal
          engine={engine}
          voices={voices}
          onClose={() => setShowCustomModal(false)}
          onUploaded={onCustomUploaded}
        />
      )}
    </div>
  )
}
