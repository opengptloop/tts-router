import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Box,
  CheckCircle2,
  Download,
  ExternalLink,
  Gauge,
  HardDrive,
  Mic2,
  RefreshCw,
  Search,
  Server,
  Trash2,
  Upload,
  Zap,
} from 'lucide-react'
import { api, formatBytes, formatTime, waitForJob } from '../api.js'
import { useApp } from '../App.jsx'
import { Badge, OptionList, Progress, Spinner, StatTile } from '../components/ui.jsx'

export function ModelsPage() {
  const { models, status, refreshModels, refreshStatus, push, update, navigate } = useApp()
  const engines = models || []

  const [variantSel, setVariantSel] = useState({})
  const [loadOptions, setLoadOptions] = useState({})
  const [engineJobs, setEngineJobs] = useState({})
  const [catalog, setCatalog] = useState(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogLanguage, setCatalogLanguage] = useState('all')
  const [catalogQuality, setCatalogQuality] = useState('all')
  const [downloadedOnly, setDownloadedOnly] = useState(false)
  const [voiceJobs, setVoiceJobs] = useState({})
  const [customVoices, setCustomVoices] = useState([])

  // ----- defaults ---------------------------------------------------------
  useEffect(() => {
    if (!engines.length) return
    setVariantSel((current) => {
      const next = { ...current }
      for (const engine of engines) {
        if (!next[engine.id]) next[engine.id] = engine.default_variant
      }
      return next
    })
  }, [engines])

  const variantFor = useCallback(
    (engine) => {
      const id = variantSel[engine.id] || engine.default_variant
      return engine.variants.find((variant) => variant.id === id) || engine.variants[0]
    },
    [variantSel],
  )

  const optionsFor = useCallback((engine, variant) => {
    const key = `${engine.id}:${variant.id}`
    if (loadOptions[key]) return loadOptions[key]
    const defaults = {}
    for (const spec of variant.load_options || []) {
      if (spec.default !== null && spec.default !== undefined) defaults[spec.key] = spec.default
    }
    return defaults
  }, [loadOptions])

  const setOption = (engine, variant, key, value) => {
    const optionKey = `${engine.id}:${variant.id}`
    setLoadOptions((current) => ({
      ...current,
      [optionKey]: { ...optionsFor(engine, variant), ...(current[optionKey] || {}), [key]: value },
    }))
  }

  // ----- install / load / unload ------------------------------------------
  const installEngine = async (engine, specKey, label) => {
    try {
      const { job_id } = await api(`/api/models/${engine.id}/install`, {
        method: 'POST',
        body: { spec: specKey },
      })
      const toastId = push({
        type: 'info',
        title: `Installing ${label}`,
        body: 'Running pip install — this can take a few minutes.',
        progress: -1,
        duration: 0,
      })
      const finished = await waitForJob(job_id, {
        onUpdate: (snapshot) => {
          setEngineJobs((current) => ({ ...current, [engine.id]: snapshot }))
          const lastLog = snapshot.logs?.[snapshot.logs.length - 1]?.message
          update(toastId, { body: lastLog || 'Working…', progress: -1 })
        },
      })
      setEngineJobs((current) => {
        const next = { ...current }
        delete next[engine.id]
        return next
      })
      if (finished.status !== 'succeeded') {
        throw new Error(finished.error || 'Install failed')
      }
      update(toastId, {
        type: 'success',
        title: `${label} installed`,
        body: 'Restart the backend to activate it, then load the model.',
        progress: null,
        duration: 8000,
      })
      await refreshModels()
      await refreshStatus()
    } catch (error) {
      push({ type: 'error', title: `Install failed`, body: error.message, duration: 12000 })
    }
  }

  const loadModel = async (engine) => {
    const variant = variantFor(engine)
    const toastId = push({
      type: 'info',
      title: `Loading ${engine.name} · ${variant.label}`,
      body: 'Downloading weights on first use…',
      progress: 0,
      duration: 0,
    })
    try {
      const { job_id } = await api(`/api/models/${engine.id}/load`, {
        method: 'POST',
        body: { variant: variant.id, options: optionsFor(engine, variant) },
      })
      const finished = await waitForJob(job_id, {
        onUpdate: (snapshot) => {
          setEngineJobs((current) => ({ ...current, [engine.id]: snapshot }))
          update(toastId, { progress: snapshot.progress || -1, body: snapshot.message })
        },
      })
      setEngineJobs((current) => {
        const next = { ...current }
        delete next[engine.id]
        return next
      })
      if (finished.status !== 'succeeded') throw new Error(finished.error || 'Load failed')
      update(toastId, {
        type: 'success',
        title: `${engine.name} loaded`,
        body: `${variant.label} on ${finished.result?.device || 'cpu'}`,
        progress: null,
        duration: 5000,
      })
      await refreshModels()
      await refreshStatus()
    } catch (error) {
      push({ type: 'error', title: 'Load failed', body: error.message, duration: 12000 })
    }
  }

  const unloadModel = async (engine) => {
    try {
      await api(`/api/models/${engine.id}/unload`, { method: 'POST' })
      push({ type: 'success', title: `${engine.name} unloaded` })
      await refreshModels()
      await refreshStatus()
    } catch (error) {
      push({ type: 'error', title: 'Unload failed', body: error.message })
    }
  }

  // ----- piper catalogue ---------------------------------------------------
  const loadCatalog = useCallback(
    async (refresh = false) => {
      setCatalogLoading(true)
      try {
        if (refresh) await api('/api/engines/piper/catalog/refresh', { method: 'POST' })
        const data = await api('/api/engines/piper/catalog')
        setCatalog(data.items)
      } catch (error) {
        if (!refresh) push({ type: 'error', title: 'Piper catalogue unavailable', body: error.message })
      } finally {
        setCatalogLoading(false)
      }
    },
    [push],
  )

  useEffect(() => {
    loadCatalog()
  }, [loadCatalog])

  const downloadPiperVoice = async (voice) => {
    setVoiceJobs((current) => ({ ...current, [voice.key]: 0.01 }))
    const toastId = push({
      type: 'info',
      title: `Downloading ${voice.key}`,
      body: formatBytes(voice.size_bytes),
      progress: 0,
      duration: 0,
    })
    try {
      const { job_id } = await api(`/api/engines/piper/voices/${voice.key}/download`, {
        method: 'POST',
      })
      const finished = await waitForJob(job_id, {
        onUpdate: (snapshot) => {
          setVoiceJobs((current) => ({ ...current, [voice.key]: snapshot.progress }))
          update(toastId, { progress: snapshot.progress, body: snapshot.message })
        },
      })
      if (finished.status !== 'succeeded') throw new Error(finished.error || 'Download failed')
      update(toastId, {
        type: 'success',
        title: `Voice ready: ${voice.key}`,
        progress: null,
        duration: 4000,
      })
      setCatalog((current) =>
        (current || []).map((item) =>
          item.key === voice.key ? { ...item, status: 'downloaded' } : item,
        ),
      )
    } catch (error) {
      update(toastId, {
        type: 'error',
        title: 'Download failed',
        body: error.message,
        progress: null,
        duration: 10000,
      })
    } finally {
      setVoiceJobs((current) => {
        const next = { ...current }
        delete next[voice.key]
        return next
      })
    }
  }

  const deletePiperVoice = async (voice) => {
    try {
      await api(`/api/engines/piper/voices/${voice.key}`, { method: 'DELETE' })
      setCatalog((current) =>
        (current || []).map((item) =>
          item.key === voice.key ? { ...item, status: 'missing' } : item,
        ),
      )
      push({ type: 'success', title: `Deleted ${voice.key}` })
    } catch (error) {
      push({ type: 'error', title: 'Delete failed', body: error.message })
    }
  }

  // ----- custom voices -----------------------------------------------------
  const loadCustomVoices = useCallback(async () => {
    try {
      const data = await api('/api/voices/custom')
      setCustomVoices(data.voices)
    } catch {
      /* offline */
    }
  }, [])

  useEffect(() => {
    loadCustomVoices()
  }, [loadCustomVoices])

  const deleteCustomVoice = async (voice) => {
    try {
      await api(`/api/voices/custom/${voice.engine}/${voice.id}`, { method: 'DELETE' })
      push({ type: 'success', title: `Deleted custom voice '${voice.name}'` })
      loadCustomVoices()
    } catch (error) {
      push({ type: 'error', title: 'Delete failed', body: error.message })
    }
  }

  // ----- filtering ---------------------------------------------------------
  const languages = useMemo(
    () =>
      catalog
        ? [...new Set(catalog.map((item) => item.language.code).filter(Boolean))].sort()
        : [],
    [catalog],
  )
  const qualities = useMemo(
    () => (catalog ? [...new Set(catalog.map((item) => item.quality).filter(Boolean))].sort() : []),
    [catalog],
  )
  const filteredCatalog = useMemo(() => {
    let items = catalog || []
    if (catalogQuery) {
      const query = catalogQuery.toLowerCase()
      items = items.filter((item) =>
        [item.key, item.name, item.language.name_english, item.language.country_english]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query)),
      )
    }
    if (catalogLanguage !== 'all') items = items.filter((item) => item.language.code === catalogLanguage)
    if (catalogQuality !== 'all') items = items.filter((item) => item.quality === catalogQuality)
    if (downloadedOnly) items = items.filter((item) => item.status === 'downloaded')
    return items
  }, [catalog, catalogQuery, catalogLanguage, catalogQuality, downloadedOnly])

  const downloadedCount = (catalog || []).filter((item) => item.status === 'downloaded').length

  const engineIcons = { kokoro: '🌊', kitten: '🐱', pocket: '🎒', piper: '🎵' }

  return (
    <div className="fade-in">
      {/* ---------------------------- system ---------------------------- */}
      {status && (
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">
                <Server size={17} style={{ color: 'var(--accent)' }} /> System
              </h2>
              <p className="card-subtitle">
                Python {status.python.version} · {status.platform}
              </p>
            </div>
            <Badge tone="neutral" className="mono">
              PID {status.pid}
            </Badge>
          </div>
          <div className="grid-4">
            <StatTile
              label="CPU"
              value={`${Math.round(status.cpu.percent)}%`}
              detail={`${status.cpu.count} threads${status.cpu.freq_mhz ? ` · ${status.cpu.freq_mhz} MHz` : ''}`}
              percent={status.cpu.percent}
            />
            <StatTile
              label="Memory"
              value={`${Math.round(status.ram.percent)}%`}
              detail={`${formatBytes(status.ram.used)} / ${formatBytes(status.ram.total)}`}
              percent={status.ram.percent}
            />
            <StatTile
              label="Disk (data dir)"
              value={formatBytes(status.disk.free)}
              detail={`free of ${formatBytes(status.disk.total)}`}
              percent={((status.disk.total - status.disk.free) / status.disk.total) * 100}
            />
            <StatTile
              label="PyTorch"
              value={status.torch || 'not installed'}
              detail={
                status.gpus.length
                  ? status.gpus.map((gpu) => gpu.name).join(', ')
                  : 'CPU inference'
              }
            />
          </div>
          {status.gpus.length > 0 && (
            <>
              <div className="divider" />
              <div className="grid-2">
                {status.gpus.map((gpu) => (
                  <StatTile
                    key={gpu.index}
                    label={`GPU ${gpu.index} · CUDA ${gpu.cuda || '?'}`}
                    value={gpu.name}
                    detail={`${formatBytes(gpu.vram_used)} / ${formatBytes(gpu.vram_total)} VRAM`}
                    percent={(gpu.vram_used / gpu.vram_total) * 100}
                  />
                ))}
              </div>
            </>
          )}
          <div className="divider" />
          <div className="row wrap" style={{ gap: 18 }}>
            <span className="small muted row" style={{ gap: 6 }}>
              <HardDrive size={13} /> HF weights cache: {formatBytes(status.cache_bytes.hf_cache)}
            </span>
            <span className="small muted row" style={{ gap: 6 }}>
              <Mic2 size={13} /> Piper voices: {formatBytes(status.cache_bytes.piper_voices)}
            </span>
            <span className="small muted row" style={{ gap: 6 }}>
              <Box size={13} /> Generated audio: {formatBytes(status.cache_bytes.audio_outputs)}
            </span>
            <span className="small muted row" style={{ gap: 6 }}>
              <Upload size={13} /> Custom voices: {formatBytes(status.cache_bytes.custom_voices)}
            </span>
          </div>
        </div>
      )}

      {/* ---------------------------- engines --------------------------- */}
      <div className="grid-2" style={{ marginTop: 16 }}>
        {engines.map((engine) => {
          const variant = variantFor(engine)
          const job = engineJobs[engine.id]
          const jobActive = job && ['queued', 'running'].includes(job.status)
          const options = optionsFor(engine, variant)
          return (
            <div className="card" key={engine.id} style={{ marginTop: 0 }}>
              <div className="card-header">
                <div className="engine-card-head">
                  <span className="engine-icon" style={{ fontSize: 18 }}>
                    {engineIcons[engine.id] || '🎙️'}
                  </span>
                  <div>
                    <h3 className="card-title">
                      {engine.name}
                      {engine.version && <Badge tone="neutral">v{engine.version}</Badge>}
                    </h3>
                    <p className="card-subtitle">
                      {engine.license} ·{' '}
                      <a href={engine.homepage} target="_blank" rel="noreferrer">
                        source <ExternalLink size={10} style={{ verticalAlign: 'middle' }} />
                      </a>
                    </p>
                  </div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  {engine.installed ? (
                    <Badge tone="success">
                      <CheckCircle2 size={11} /> installed
                    </Badge>
                  ) : (
                    <Badge tone="warning">not installed</Badge>
                  )}
                  {engine.restart_required && (
                    <Badge tone="warning" style={{ cursor: 'help' }}>
                      restart backend
                    </Badge>
                  )}
                  {engine.loaded && (
                    <Badge tone="accent">
                      <Zap size={11} /> loaded
                    </Badge>
                  )}
                </div>
              </div>

              <p className="small muted" style={{ marginTop: 0 }}>
                {engine.description}
              </p>

              {!engine.installed && (
                <div
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    background: 'var(--panel-2)',
                    border: '1px dashed var(--border-strong)',
                    marginBottom: 12,
                  }}
                >
                  <div className="small" style={{ marginBottom: 8, fontWeight: 600 }}>
                    Install with pip
                  </div>
                  <div className="row wrap">
                    <button
                      className="btn primary sm"
                      disabled={jobActive}
                      onClick={() =>
                        installEngine(
                          engine,
                          'base',
                          `${engine.name} (${engine.install_targets?.base?.packages?.join(' ')})`,
                        )
                      }
                    >
                      {jobActive ? <Spinner /> : <Download size={13} />} Install engine
                    </button>
                    {Object.entries(engine.install_targets || {})
                      .filter(([key]) => key !== 'base')
                      .map(([key, target]) => (
                        <button
                          key={key}
                          className="btn sm"
                          disabled={jobActive}
                          onClick={() => installEngine(engine, key, target.label)}
                        >
                          <Download size={12} /> {target.label}
                        </button>
                      ))}
                  </div>
                  {engine.install_specs?.notes && (
                    <p className="small muted" style={{ margin: '8px 0 0' }}>
                      {engine.install_specs.notes}
                    </p>
                  )}
                  {job && job.kind === 'install' && (
                    <div style={{ marginTop: 10 }}>
                      <Progress value={job.progress} indeterminate />
                      <p className="small muted" style={{ margin: '6px 0 0' }}>
                        {job.logs?.[job.logs.length - 1]?.message || job.message}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {engine.installed && (
                <>
                  <div className="small muted" style={{ margin: '4px 0 8px', fontWeight: 600 }}>
                    Model variant
                  </div>
                  {engine.variants.map((item) => {
                    const selected = item.id === variant.id
                    const isLoaded =
                      engine.loaded && engine.loaded_variant === item.id
                    return (
                      <div
                        key={item.id}
                        className={`variant-item ${selected ? 'selected' : ''}`}
                        style={{ marginBottom: 8, cursor: 'pointer' }}
                        onClick={() =>
                          setVariantSel((current) => ({ ...current, [engine.id]: item.id }))
                        }
                      >
                        <div className="row between">
                          <span className="row" style={{ gap: 8 }}>
                            <input
                              type="radio"
                              checked={selected}
                              onChange={() =>
                                setVariantSel((current) => ({
                                  ...current,
                                  [engine.id]: item.id,
                                }))
                              }
                            />
                            <strong className="small">{item.label}</strong>
                            {item.cloning && <Badge tone="accent">cloning</Badge>}
                          </span>
                          <span className="row" style={{ gap: 6 }}>
                            {item.cache_status === 'downloaded' ? (
                              <Badge tone="success">weights cached</Badge>
                            ) : item.cache_status === 'unknown' ? (
                              <Badge tone="neutral">remote</Badge>
                            ) : (
                              <Badge tone="neutral">not downloaded</Badge>
                            )}
                            {isLoaded && <Badge tone="accent">loaded</Badge>}
                          </span>
                        </div>
                        <p className="small muted" style={{ margin: '6px 0 0' }}>
                          {item.description} · {item.size_hint}
                        </p>

                        {selected && (
                          <div
                            style={{ marginTop: 10 }}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <OptionList
                              specs={item.load_options}
                              values={options}
                              onChange={(key, value) => setOption(engine, item, key, value)}
                            />
                            <div className="row">
                              {isLoaded ? (
                                <button
                                  className="btn danger sm"
                                  onClick={() => unloadModel(engine)}
                                  disabled={jobActive}
                                >
                                  Unload
                                </button>
                              ) : (
                                <button
                                  className="btn primary sm"
                                  onClick={() => loadModel(engine)}
                                  disabled={jobActive}
                                >
                                  {jobActive ? <Spinner /> : <Zap size={13} />} Load model
                                </button>
                              )}
                              {isLoaded && (
                                <span className="small muted">
                                  on {engine.device || 'cpu'} since{' '}
                                  {formatTime(engine.loaded_at)}
                                </span>
                              )}
                            </div>
                            {jobActive && (
                              <div style={{ marginTop: 10 }}>
                                <Progress value={job.progress} />
                                <p className="small muted" style={{ margin: '6px 0 0' }}>
                                  {job.message}
                                </p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* ---------------------------- piper voices ---------------------- */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">
              <Mic2 size={17} style={{ color: 'var(--accent)' }} /> Piper voice catalog
            </h2>
            <p className="card-subtitle">
              {catalog
                ? `${downloadedCount} of ${catalog.length} voices downloaded · cached locally`
                : 'Official rhasspy/piper-voices catalogue'}
            </p>
          </div>
          <button
            className="btn sm"
            onClick={() => loadCatalog(true)}
            disabled={catalogLoading}
          >
            {catalogLoading ? <Spinner /> : <RefreshCw size={13} />} Refresh catalog
          </button>
        </div>

        <div className="row wrap" style={{ marginBottom: 12 }}>
          <div className="row" style={{ flex: 1, minWidth: 220, gap: 8 }}>
            <Search size={15} className="muted" />
            <input
              className="input"
              placeholder="Search voices (name, language, country)…"
              value={catalogQuery}
              onChange={(event) => setCatalogQuery(event.target.value)}
            />
          </div>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={catalogLanguage}
            onChange={(event) => setCatalogLanguage(event.target.value)}
          >
            <option value="all">All languages ({languages.length})</option>
            {languages.map((language) => (
              <option key={language} value={language}>
                {language}
              </option>
            ))}
          </select>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={catalogQuality}
            onChange={(event) => setCatalogQuality(event.target.value)}
          >
            <option value="all">All qualities</option>
            {qualities.map((quality) => (
              <option key={quality} value={quality}>
                {quality}
              </option>
            ))}
          </select>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={downloadedOnly}
              onChange={(event) => setDownloadedOnly(event.target.checked)}
            />
            Downloaded only
          </label>
        </div>

        {catalogLoading && !catalog && (
          <div className="row muted" style={{ padding: 20 }}>
            <Spinner /> Loading catalogue…
          </div>
        )}

        {catalog && (
          <div className="table-wrap" style={{ maxHeight: 480, overflowY: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Voice</th>
                  <th>Language</th>
                  <th>Quality</th>
                  <th>Speakers</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredCatalog.slice(0, 400).map((voice) => (
                  <tr key={voice.key}>
                    <td>
                      <span className="mono" style={{ fontSize: 12 }}>{voice.key}</span>
                    </td>
                    <td>
                      {voice.language.name_english}
                      {voice.language.country_english ? ` (${voice.language.country_english})` : ''}
                    </td>
                    <td>
                      <Badge tone="neutral">{voice.quality}</Badge>
                    </td>
                    <td>{voice.num_speakers}</td>
                    <td className="mono small">{formatBytes(voice.size_bytes)}</td>
                    <td>
                      {voiceJobs[voice.key] !== undefined ? (
                        <span className="row small" style={{ gap: 6 }}>
                          <Spinner /> {Math.round((voiceJobs[voice.key] || 0) * 100)}%
                        </span>
                      ) : voice.status === 'downloaded' ? (
                        <Badge tone="success">downloaded</Badge>
                      ) : voice.status === 'partial' ? (
                        <Badge tone="warning">partial</Badge>
                      ) : (
                        <Badge tone="neutral">not downloaded</Badge>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
                        {voice.status !== 'downloaded' ? (
                          <button
                            className="btn sm"
                            disabled={voiceJobs[voice.key] !== undefined}
                            onClick={() => downloadPiperVoice(voice)}
                          >
                            <Download size={12} /> Download
                          </button>
                        ) : (
                          <button
                            className="btn danger sm"
                            onClick={() => deletePiperVoice(voice)}
                            title="Delete local files"
                          >
                            <Trash2 size={12} />
                          </button>
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredCatalog.length === 0 && (
              <div className="voice-empty">No voices match these filters.</div>
            )}
            {filteredCatalog.length > 400 && (
              <div className="voice-empty">
                Showing first 400 of {filteredCatalog.length} — refine your search.
              </div>
            )}
          </div>
        )}

        <p className="small muted" style={{ marginBottom: 0, marginTop: 10 }}>
          Voices are downloaded on demand from <span className="mono">rhasspy/piper-voices</span> and
          reused by the Studio and the Piper engine.
        </p>
      </div>

      {/* ---------------------------- custom voices --------------------- */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">
              <Gauge size={17} style={{ color: 'var(--accent)' }} /> Custom voices
            </h2>
            <p className="card-subtitle">
              Voice tensors, reference clips and ONNX voices you added
            </p>
          </div>
          <button className="btn sm" onClick={() => navigate('studio')}>
            <Upload size={13} /> Add in Studio
          </button>
        </div>
        {customVoices.length === 0 && (
          <p className="muted small">
            No custom voices yet. Use <strong>+ Custom</strong> in the Studio to upload a Kokoro
            <span className="mono"> .pt</span> tensor, a reference clip for KittenTTS 2 / Pocket TTS,
            or a Piper <span className="mono">.onnx + .onnx.json</span> pair.
          </p>
        )}
        {customVoices.map((voice) => (
          <div key={`${voice.engine}:${voice.id}`} className="history-item">
            <Badge tone="accent">{voice.engine}</Badge>
            <div className="meta">
              <div className="text" style={{ fontWeight: 600, color: 'var(--text)' }}>
                {voice.name}
              </div>
              <div className="sub">
                {voice.kind} · {voice.files.join(', ')} · {formatBytes(voice.size_bytes)} ·{' '}
                {voice.created_at_iso}
              </div>
            </div>
            <button
              className="btn danger sm"
              onClick={() => deleteCustomVoice(voice)}
              title="Delete"
            >
              <Trash2 size={12} /> Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
