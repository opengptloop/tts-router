import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  Info,
  KeyRound,
  Link2,
  Play,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import { api, formatTime } from '../api.js'
import { useApp } from '../App.jsx'
import { Badge, Field, Modal, Spinner } from '../components/ui.jsx'

const FORMATS = ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm']
const PLAYABLE_FORMATS = new Set(['mp3', 'opus', 'aac', 'flac', 'wav'])

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text)
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand('copy')
  } catch {
    /* ignore */
  }
  ta.remove()
  return Promise.resolve()
}

function CopyButton({ value, label = 'Copy', className = '' }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      className={`btn ghost sm copy-btn ${className}`}
      title={label}
      onClick={async () => {
        await copyText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1600)
      }}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? 'Copied' : label}
    </button>
  )
}

function CodeBlock({ code }) {
  return (
    <div className="code-block">
      <CopyButton value={code} className="" />
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Endpoint / base URL card
// ---------------------------------------------------------------------------

function EndpointCard({ baseUrl, status, config }) {
  const { online } = useApp()
  const needsKey = !!config?.require_api_key
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">Base URL</div>
          <div className="card-subtitle">
            One single URL. Point any OpenAI-compatible TTS client here — that is
            the whole client-side setup.
          </div>
        </div>
        <Badge tone={needsKey ? 'success' : 'info'}>
          <ShieldCheck size={12} style={{ marginRight: 5 }} />
          {needsKey ? 'API key required' : 'Open — no key needed'}
        </Badge>
      </div>
      <div className="endpoint-url">
        <Link2 size={16} style={{ color: 'var(--accent)' }} />
        <code>{baseUrl}</code>
        <CopyButton value={baseUrl} />
      </div>
      <div className="callout" style={{ marginTop: 12 }}>
        <Info size={16} />
        <span>
          <strong>Clients only send two things:</strong>{' '}
          <code className="mono">input</code> (the text) and optionally{' '}
          <code className="mono">output</code> (the audio format). They never
          pick models, voices or settings — everything is configured right here
          on this page, once.
        </span>
      </div>
      <div className="row wrap" style={{ marginTop: 12, gap: 8 }}>
        <Badge tone="neutral">POST {baseUrl}/audio/speech</Badge>
        <Badge tone={online ? 'success' : 'danger'}>
          {online ? 'backend online' : 'backend offline'}
        </Badge>
        {config?.configured ? (
          <Badge tone="success">
            model: {config.engine} · voice: {config.voice}
          </Badge>
        ) : (
          <Badge tone="warning">no model configured yet</Badge>
        )}
        {status?.ffmpeg_available ? (
          <Badge tone="info">ffmpeg ready · all formats</Badge>
        ) : (
          <Badge tone="warning">no ffmpeg · wav / flac / pcm only</Badge>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Configuration — the one place the TTS setup happens
// ---------------------------------------------------------------------------

function ConfigSection({ config, reload, push }) {
  const engines = useMemo(() => config?.engines || [], [config])
  const snapshot = useMemo(
    () =>
      JSON.stringify({
        engine: config?.engine || '',
        variant: config?.variant || '',
        voice: config?.voice || '',
        speed: config?.speed ?? 1.0,
        response_format: config?.response_format || 'mp3',
        max_input_chars: config?.max_input_chars ?? 4096,
      }),
    [config],
  )
  const [form, setForm] = useState(snapshot)
  const [voices, setVoices] = useState([])
  const [voicesLoading, setVoicesLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const parsed = useMemo(() => JSON.parse(form), [form])
  const dirty = form !== snapshot
  const engine = engines.find((e) => e.id === parsed.engine) || null

  // Re-sync the form when a save (or a background reload) lands and there are
  // no local edits to lose.
  useEffect(() => {
    setForm((current) => (current === snapshot ? current : dirty ? current : snapshot))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshot])

  const set = (patch) => setForm(JSON.stringify({ ...parsed, ...patch }))

  // Load the voice list for the selected engine. For Piper only downloaded
  // (installed) voices are offered; built-in engine voices are always offered.
  useEffect(() => {
    let cancelled = false
    if (!engine || !engine.installed) {
      setVoices([])
      return
    }
    setVoicesLoading(true)
    const params = new URLSearchParams()
    if (parsed.variant) params.set('variant', parsed.variant)
    api(`/api/engines/${engine.id}/voices?${params.toString()}`)
      .then((data) => {
        if (cancelled) return
        const all = data.voices || []
        setVoices(all.filter((v) => v.downloaded !== false))
      })
      .catch(() => {
        if (!cancelled) setVoices([])
      })
      .finally(() => {
        if (!cancelled) setVoicesLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine?.id, parsed.variant, engine?.installed])

  const voiceIds = useMemo(() => new Set(voices.map((v) => v.id)), [voices])
  const voiceMissing = parsed.voice && !voiceIds.has(parsed.voice)

  const anyInstalled = engines.some((e) => e.installed)
  const isPiper = engine?.id === 'piper'

  const save = async () => {
    if (!parsed.engine) {
      push({ type: 'error', title: 'Pick a model', body: 'Choose the TTS model that will serve the API.' })
      return
    }
    if (!parsed.voice) {
      push({ type: 'error', title: 'Pick a voice', body: 'Choose the voice clients will hear.' })
      return
    }
    setSaving(true)
    try {
      const saved = await api('/api/openai/config', {
        method: 'PUT',
        body: {
          engine: parsed.engine,
          variant: parsed.variant || null,
          voice: parsed.voice,
          speed: Number(parsed.speed) || 1.0,
          response_format: parsed.response_format,
          max_input_chars: Number(parsed.max_input_chars) || 4096,
          require_api_key: !!config?.require_api_key,
        },
      })
      push({
        type: 'success',
        title: 'Configuration saved',
        body: saved.engine_loading
          ? 'Clients can now generate speech. The model is warming up in the background — the first request may take a few extra seconds.'
          : 'Clients can now generate speech with the configured model and voice.',
      })
      await reload()
    } catch (error) {
      push({ type: 'error', title: 'Could not save configuration', body: error.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">Configuration</div>
          <div className="card-subtitle">
            Pick the TTS model and voice that answer the API. This is the only
            setup clients ever rely on — they just send text.
          </div>
        </div>
        {dirty && <Badge tone="warning">unsaved changes</Badge>}
      </div>

      {!anyInstalled && (
        <div className="callout warning" style={{ marginBottom: 12 }}>
          <TriangleAlert size={16} />
          <span>
            No TTS model is installed yet. Install one on the{' '}
            <strong>Models &amp; Config</strong> page first, then come back here
            to finish the setup.
          </span>
        </div>
      )}

      <div className="grid-2" style={{ gap: 12 }}>
        <Field
          label="1 · TTS model"
          help={
            engine && !engine.loaded && engine.installed
              ? 'Will be loaded automatically when you save (or on the first request).'
              : 'Only installed models can be selected.'
          }
        >
          <select
            className="select"
            value={parsed.engine}
            onChange={(e) => set({ engine: e.target.value, variant: '', voice: '' })}
          >
            <option value="">{anyInstalled ? 'Select model…' : 'No model installed…'}</option>
            {engines.map((e) => (
              <option key={e.id} value={e.id} disabled={!e.installed}>
                {e.name}
                {e.installed
                  ? e.loaded
                    ? ' · ready'
                    : ''
                  : ' — install required'}
              </option>
            ))}
          </select>
        </Field>
        {engine && engine.variants.length > 1 && (
          <Field label="Variant" help="Model size / flavour inside the engine.">
            <select
              className="select"
              value={parsed.variant || ''}
              onChange={(e) => set({ variant: e.target.value || '', voice: '' })}
            >
              <option value="">Engine default</option>
              {engine.variants.map((v) => (
                <option key={v.id} value={v.id}>{v.label || v.id}</option>
              ))}
            </select>
          </Field>
        )}
      </div>

      {engine && engine.installed && (
        <Field
          label="2 · Voice"
          help={
            isPiper
              ? `Showing the ${voices.length} downloaded voice${voices.length === 1 ? '' : 's'} — download more from the Models & Config page.`
              : 'Voices built into this model.'
          }
        >
          {voicesLoading ? (
            <span className="help"><Spinner /> loading voices…</span>
          ) : voices.length === 0 ? (
            <div className="callout warning">
              <TriangleAlert size={15} />
              <span>
                No downloaded voices yet for {engine.name}. Download one from
                the <strong>Models &amp; Config</strong> page, then pick it here.
              </span>
            </div>
          ) : (
            <select
              className="select"
              value={parsed.voice}
              onChange={(e) => set({ voice: e.target.value })}
            >
              <option value="">Select voice…</option>
              {voiceMissing && parsed.voice && (
                <option value={parsed.voice}>{parsed.voice} (saved)</option>
              )}
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name?.split('·')[0]?.trim() || v.id}
                  {v.language ? ` — ${v.language}` : ''}
                </option>
              ))}
            </select>
          )}
        </Field>
      )}

      <div className="grid-2" style={{ gap: 12, marginTop: 4 }}>
        <Field label="3 · Speed" help="0.25 – 4.0, applied to every request.">
          <input
            className="input"
            type="number"
            min={0.25}
            max={4}
            step={0.05}
            value={parsed.speed}
            onChange={(e) => set({ speed: e.target.value })}
          />
        </Field>
        <Field
          label="Default output format"
          help="Used when the client does not ask for a specific format."
        >
          <select
            className="select"
            value={parsed.response_format}
            onChange={(e) => set({ response_format: e.target.value })}
          >
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
                {config?.formats_available && !config.formats_available[f] ? ' (unavailable)' : ''}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Max input length" help="Characters accepted per request.">
          <input
            className="input"
            type="number"
            min={1}
            max={100000}
            value={parsed.max_input_chars}
            onChange={(e) => set({ max_input_chars: e.target.value })}
          />
        </Field>
      </div>

      <div className="row between" style={{ marginTop: 12 }}>
        <span className="small muted">
          {engine && !engine.loaded && engine.installed
            ? 'The model starts loading as soon as you save.'
            : 'Saved settings apply immediately.'}
        </span>
        <button
          className="btn primary sm"
          disabled={saving || !dirty || !parsed.engine || !parsed.voice || !engine?.installed}
          onClick={save}
        >
          {saving ? <Spinner /> : <Save size={14} />} Save configuration
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// API keys — optional by default
// ---------------------------------------------------------------------------

function maskKey(key) {
  if (!key) return ''
  return `${key.slice(0, 12)}…${key.slice(-4)}`
}

function CreateKeyModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [rateLimit, setRateLimit] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)

  const create = async () => {
    setBusy(true)
    try {
      const data = await api('/api/openai/keys', {
        method: 'POST',
        body: {
          name: name.trim() || 'Untitled key',
          rate_limit_per_min: rateLimit ? Number(rateLimit) : null,
        },
      })
      setCreated(data.key)
      onCreated(data.key)
    } catch (error) {
      onCreated(null, error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={created ? 'API key created' : 'Create API key'} onClose={onClose} width={520}>
      {created ? (
        <>
          <div className="callout warning" style={{ marginBottom: 12 }}>
            <TriangleAlert size={16} />
            <span>Copy this key now — it is shown in full on the keys list, but
              treat it like a password when sharing it with clients.</span>
          </div>
          <div className="endpoint-url">
            <KeyRound size={15} />
            <code>{created.key}</code>
            <CopyButton value={created.key} />
          </div>
          <div className="row between" style={{ marginTop: 14 }}>
            <span className="small muted">
              {created.rate_limit_per_min
                ? `Rate limit: ${created.rate_limit_per_min} requests/min`
                : 'No rate limit'}
            </span>
            <button className="btn primary sm" onClick={onClose}>Done</button>
          </div>
        </>
      ) : (
        <>
          <Field label="Key name" help="A label so you remember where this key is used.">
            <input
              className="input"
              value={name}
              autoFocus
              placeholder="e.g. SillyTavern, my-script, Cursor"
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field label="Rate limit (requests per minute)" help="Leave empty for unlimited. Only applies when keys are required.">
            <input
              className="input"
              type="number"
              min={0}
              placeholder="unlimited"
              value={rateLimit}
              onChange={(e) => setRateLimit(e.target.value)}
            />
          </Field>
          <div className="row between" style={{ marginTop: 10 }}>
            <button className="btn ghost sm" onClick={onClose}>Cancel</button>
            <button className="btn primary sm" disabled={busy} onClick={create}>
              {busy ? <Spinner /> : <Plus size={14} />} Create key
            </button>
          </div>
        </>
      )}
    </Modal>
  )
}

function KeysSection({ keys, status, config, reload, push }) {
  const [showModal, setShowModal] = useState(false)
  const [revealed, setRevealed] = useState({})
  const [toggling, setToggling] = useState(false)
  const needsKey = !!config?.require_api_key

  const toggleAuth = async (event) => {
    const require = event.target.checked
    setToggling(true)
    try {
      await api('/api/openai/config/auth', {
        method: 'PATCH',
        body: { require_api_key: require },
      })
      push({
        type: 'success',
        title: require ? 'API key now required' : 'API is now open',
        body: require
          ? 'Clients must send Authorization: Bearer <key> to generate speech.'
          : 'Anyone who can reach this server can generate speech — no key needed.',
      })
      reload()
    } catch (error) {
      push({ type: 'error', title: 'Could not change auth mode', body: error.message })
    } finally {
      setToggling(false)
    }
  }

  const removeKey = async (key) => {
    if (!window.confirm(`Delete key "${key.name}"? Clients using it will stop working.`)) return
    try {
      await api(`/api/openai/keys/${key.id}`, { method: 'DELETE' })
      push({ type: 'success', title: 'Key deleted', body: `"${key.name}" was removed.` })
      reload()
    } catch (error) {
      push({ type: 'error', title: 'Could not delete key', body: error.message })
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">API keys (optional)</div>
          <div className="card-subtitle">
            The API is open by default — keys are entirely up to you.
          </div>
        </div>
        <button className="btn primary sm" onClick={() => setShowModal(true)}>
          <Plus size={14} /> New key
        </button>
      </div>

      <label className="toggle-row" style={{ marginBottom: 12 }}>
        <input type="checkbox" checked={needsKey} disabled={toggling} onChange={toggleAuth} />
        Require an API key for every request
        {toggling && <Spinner />}
      </label>

      {needsKey ? (
        <div className="callout warning" style={{ marginBottom: 12 }}>
          <TriangleAlert size={16} />
          <span>
            Keys are required: clients must send{' '}
            <code className="mono">Authorization: Bearer &lt;key&gt;</code>.
            {status?.keys_active
              ? ` ${status.keys_active} active key${status.keys_active === 1 ? '' : 's'} on file.`
              : ' No keys yet — create one below, otherwise no client can call the API.'}
          </span>
        </div>
      ) : (
        <div className="callout" style={{ marginBottom: 12 }}>
          <Info size={16} />
          <span>
            <strong>Open mode:</strong> anyone who can reach this server can
            generate speech — no key needed. Keys you create still work: when a
            client sends one, usage stats and rate limits apply to that key.
          </span>
        </div>
      )}

      {keys.length === 0 ? (
        <div className="small muted" style={{ padding: '8px 0 4px' }}>
          No API keys yet. In open mode you do not need any — create one only if
          you want per-client usage tracking or rate limits.
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Key</th>
                <th>Requests</th>
                <th>Rate limit</th>
                <th>Last used</th>
                <th style={{ width: 90 }}></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} style={key.revoked ? { opacity: 0.45 } : undefined}>
                  <td>
                    <strong>{key.name}</strong>
                    {key.revoked && <Badge tone="danger" style={{ marginLeft: 8 }}>revoked</Badge>}
                  </td>
                  <td>
                    <span className="row" style={{ gap: 6 }}>
                      <span className="masked-key">
                        {revealed[key.id] ? key.key : maskKey(key.key)}
                      </span>
                      <button
                        className="btn ghost icon"
                        style={{ width: 26, height: 26 }}
                        title={revealed[key.id] ? 'Hide' : 'Reveal'}
                        onClick={() => setRevealed((r) => ({ ...r, [key.id]: !r[key.id] }))}
                      >
                        {revealed[key.id] ? <EyeOff size={13} /> : <Eye size={13} />}
                      </button>
                      <CopyButton value={key.key} label="" className="" />
                    </span>
                  </td>
                  <td className="mono">{key.request_count || 0}</td>
                  <td>{key.rate_limit_per_min ? `${key.rate_limit_per_min}/min` : '—'}</td>
                  <td className="small muted">{key.last_used_at ? formatTime(key.last_used_at) : 'never'}</td>
                  <td>
                    <button className="btn ghost icon" title="Delete key" onClick={() => removeKey(key)}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <CreateKeyModal
          onClose={() => setShowModal(false)}
          onCreated={(key, error) => {
            if (error) {
              push({ type: 'error', title: 'Could not create key', body: error.message })
              return
            }
            reload()
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Code examples — the whole client is: base URL (+ key if required) + input
// ---------------------------------------------------------------------------

function ExamplesSection({ baseUrl, config, keys }) {
  const [tab, setTab] = useState('curl')
  const needsKey = !!config?.require_api_key
  const apiKey = '<YOUR_API_KEY>'
  const defaultFormat = config?.response_format || 'mp3'
  const engine = config?.engine || 'your-model'
  const voice = config?.voice || 'your-voice'

  const authCurl = needsKey ? `  -H "Authorization: Bearer ${apiKey}" \\\n` : ''
  const curl = `curl ${baseUrl}/audio/speech \\
${authCurl}  -H "Content-Type: application/json" \\
  -d '{"input": "Today is a wonderful day to build something people love!"}' \\
  --output speech.mp3`
  const curlFormat = `# ask for a specific audio format (default: ${defaultFormat})
curl ${baseUrl}/audio/speech \\
${authCurl}  -H "Content-Type: application/json" \\
  -d '{"input": "Hello!", "output": "wav"}' \\
  --output speech.wav`

  const sdkKey = needsKey ? apiKey : 'not-needed'
  const python = `# pip install openai
from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}",
    api_key="${sdkKey}",${needsKey ? '' : '  # open mode: any non-empty string works'}
)

with client.audio.speech.with_streaming_response.create(
    model="tts-1",   # required by the SDK — your server ignores it
    voice="alloy",   # required by the SDK — your server ignores it
    input="Today is a wonderful day to build something people love!",
) as response:
    response.stream_to_file("speech.mp3")`

  const node = `// npm install openai
import OpenAI from "openai";
import { writeFile } from "node:fs/promises";

const client = new OpenAI({
  baseURL: "${baseUrl}",
  apiKey: "${sdkKey}",${needsKey ? '' : ' // open mode: any non-empty string works'}
});

const mp3 = await client.audio.speech.create({
  model: "tts-1",   // required by the SDK — your server ignores it
  voice: "alloy",   // required by the SDK — your server ignores it
  input: "Today is a wonderful day to build something people love!",
});

const buffer = Buffer.from(await mp3.arrayBuffer());
await writeFile("speech.mp3", buffer);`

  const pythonPlain = `# pip install requests
import requests

response = requests.post(
    "${baseUrl}/audio/speech",
    json={"input": "Today is a wonderful day to build something people love!"},${needsKey ? `\n    headers={"Authorization": "Bearer ${apiKey}"},` : ''}
)
response.raise_for_status()
open("speech.mp3", "wb").write(response.content)`

  const http = `POST ${baseUrl}/audio/speech
${needsKey ? `Authorization: Bearer ${apiKey}\n` : ''}Content-Type: application/json

{
  "input": "Today is a wonderful day to build something people love!"
}

// 200 OK
// Content-Type: audio/mpeg
// X-Model: ${engine}
// X-Voice: ${voice}
// <audio bytes>`

  const tabs = [
    { id: 'curl', label: 'cURL', code: curl },
    { id: 'python-plain', label: 'Python (requests)', code: pythonPlain },
    { id: 'python', label: 'Python (openai)', code: python },
    { id: 'node', label: 'JavaScript / TypeScript', code: node },
    { id: 'http', label: 'Raw HTTP', code: http },
    { id: 'others', label: 'Other clients' },
  ]

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">Code examples</div>
          <div className="card-subtitle">
            The entire client: this base URL{needsKey ? ', an API key,' : ''} and the
            text. Nothing else to configure.
          </div>
        </div>
      </div>
      <div className="code-tabs">
        {tabs.map((t) => (
          <button key={t.id} className={`code-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'curl' ? (
        <>
          <CodeBlock code={curl} />
          <div style={{ height: 10 }} />
          <CodeBlock code={curlFormat} />
        </>
      ) : tab === 'others' ? (
        <div className="small" style={{ lineHeight: 1.7 }}>
          <p><strong>SillyTavern</strong> — Extensions → Speech Recognition &amp; Synthesis → TTS Provider “OpenAI”. Set the custom endpoint to <code className="mono">{baseUrl}</code>{needsKey ? ' and paste an API key' : ' (leave the API key field as any placeholder text)'} — whatever model/voice its UI sends, your configured model and voice are used.</p>
          <p><strong>Any tool with a custom “OpenAI base URL”</strong> (Cursor, LangChain, Home Assistant, Telegram bots…): set the base URL to <code className="mono">{baseUrl}</code>{needsKey ? ', paste an API key,' : ','} and send your text. Extra fields these tools send are accepted but ignored.</p>
          <p className="muted">Everything is generated locally by the model you configured above. No data leaves this machine.</p>
        </div>
      ) : (
        <CodeBlock code={tabs.find((t) => t.id === tab).code} />
      )}
      <div className="code-note">
        {needsKey ? (
          <>Replace <code className="mono">{apiKey}</code> with one of your keys from the API keys section{keys?.length ? '' : ' (create one above)'}.</>
        ) : (
          <>Open mode: no API key needed. OpenAI SDKs require the <code className="mono">model</code> / <code className="mono">voice</code> arguments — pass any value, your server always uses its own configuration.</>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// API reference
// ---------------------------------------------------------------------------

function ReferenceSection({ config }) {
  const formats = config?.formats_available || {}
  const rows = [
    ['input', 'string', 'The text to synthesize. This is the only required field.', 'required'],
    ['output', 'string', 'Audio format: mp3, opus, aac, flac, wav, pcm. Defaults to the configured format.', 'optional'],
    ['response_format', 'string', 'Same as output — accepted so existing OpenAI clients keep working.', 'optional'],
    ['model', 'string', 'Accepted for compatibility, ignored. The configured model always answers.', 'ignored'],
    ['voice', 'string', 'Accepted for compatibility, ignored. The configured voice always answers.', 'ignored'],
    ['speed', 'number', 'Accepted for compatibility, ignored. The configured speed always applies.', 'ignored'],
  ]
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">Request reference</div>
          <div className="card-subtitle"><code className="mono">POST /v1/audio/speech</code> · OpenAI-compatible errors (<code className="mono">{`{"error": {"message", "type", "param", "code"}}`}</code>)</div>
        </div>
      </div>
      <div className="table-wrap param-table">
        <table className="table">
          <thead>
            <tr><th>Parameter</th><th>Type</th><th>Description</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map(([name, type, desc, req]) => (
              <tr key={name}>
                <td><code>{name}</code></td>
                <td className="small muted">{type}</td>
                <td className="small">{desc}</td>
                <td>
                  <Badge tone={req === 'required' ? 'accent' : req === 'ignored' ? 'neutral' : 'info'}>
                    {req}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row wrap" style={{ marginTop: 12, gap: 8 }}>
        <span className="small muted" style={{ width: '100%' }}>Output formats:</span>
        {FORMATS.map((f) => (
          <Badge key={f} tone={formats[f] ? 'success' : 'danger'}>
            {f}{formats[f] ? '' : ' (unavailable)'}
          </Badge>
        ))}
      </div>
      <div className="code-note">
        Errors: no model configured answers <code className="mono">400 model_not_configured</code>;
        input over the configured limit answers <code className="mono">400 input_too_long</code>;
        missing/invalid keys answer <code className="mono">401</code> (only when keys are
        required); a key past its rate limit answers <code className="mono">429</code>; a model
        still warming up answers <code className="mono">503 model_loading</code> — retry shortly.
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Test console — the request your clients will make
// ---------------------------------------------------------------------------

function TestConsole({ config, keys }) {
  const [format, setFormat] = useState(config?.response_format || 'mp3')
  const [input, setInput] = useState('Hello! This audio was generated by your own local TTS server.')
  const [keyId, setKeyId] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null) // {url, ms, size, status}
  const [error, setError] = useState(null)
  const { push } = useApp()
  const needsKey = !!config?.require_api_key

  useEffect(() => {
    if (config?.response_format) setFormat(config.response_format)
  }, [config?.response_format])

  const run = async () => {
    setBusy(true)
    setError(null)
    if (result?.url) URL.revokeObjectURL(result.url)
    setResult(null)
    const started = performance.now()
    try {
      const key = keys?.find((k) => k.id === keyId)
      const res = await fetch('/v1/audio/speech', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(key ? { Authorization: `Bearer ${key.key}` } : {}),
        },
        body: JSON.stringify({ input, output: format }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => null)
        throw new Error(data?.error?.message || `Request failed (${res.status})`)
      }
      const blob = await res.blob()
      const ms = Math.round(performance.now() - started)
      setResult({ url: URL.createObjectURL(blob), ms, size: blob.size, status: res.status })
    } catch (err) {
      setError(err.message)
      push({ type: 'error', title: 'Test request failed', body: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card test-console">
      <div className="card-header">
        <div>
          <div className="card-title">Test console</div>
          <div className="card-subtitle">
            Exactly what a client sends — text in, audio out.
          </div>
        </div>
        <Badge tone={config?.configured ? 'success' : 'warning'}>
          {config?.configured ? `model: ${config.engine}` : 'not configured yet'}
        </Badge>
      </div>
      <div className="grid-2" style={{ gap: 12 }}>
        <Field label="Output format" help="Optional — omit it to use the configured default.">
          <select className="select" value={format} onChange={(e) => setFormat(e.target.value)}>
            {FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </Field>
        {needsKey && (
          <Field label="API key" help="Required — keys are enforced in this mode.">
            <select className="select" value={keyId} onChange={(e) => setKeyId(e.target.value)}>
              <option value="">Select key…</option>
              {(keys || []).map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
            </select>
          </Field>
        )}
      </div>
      <Field label="Input text">
        <textarea className="input" rows={3} value={input} onChange={(e) => setInput(e.target.value)} />
      </Field>
      <div className="row" style={{ gap: 10 }}>
        <button className="btn primary sm" disabled={busy || !config?.configured} onClick={run}>
          {busy ? <Spinner /> : <Play size={14} />} Send test request
        </button>
        {result && (
          <span className="small muted">
            <Badge tone="success">HTTP {result.status}</Badge> · {result.ms} ms ·{' '}
            {(result.size / 1024).toFixed(1)} KiB · {format}
          </span>
        )}
      </div>
      {!config?.configured && (
        <div className="code-note">Complete the configuration above — pick a model and voice, then save.</div>
      )}
      {error && (
        <div className="callout warning" style={{ marginTop: 10 }}>
          <TriangleAlert size={15} />
          <span>{error}</span>
        </div>
      )}
      {result && PLAYABLE_FORMATS.has(format) && <audio controls src={result.url} />}
      {result && !PLAYABLE_FORMATS.has(format) && (
        <div className="code-note">Raw PCM cannot be played inline — download it with cURL instead.</div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ApiPage() {
  const { push } = useApp()
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [keys, setKeys] = useState([])
  const [loaded, setLoaded] = useState(false)
  const baseUrl = useMemo(() => `${window.location.origin}/v1`, [])

  const reload = useCallback(async () => {
    try {
      const [s, c, k] = await Promise.all([
        api('/api/openai/status'),
        api('/api/openai/config'),
        api('/api/openai/keys'),
      ])
      setStatus(s)
      setConfig(c)
      setKeys(k.keys)
    } catch (error) {
      push({ type: 'error', title: 'Could not load API settings', body: error.message })
    } finally {
      setLoaded(true)
    }
  }, [push])

  useEffect(() => {
    reload()
  }, [reload])

  if (!loaded) {
    return (
      <div className="row" style={{ justifyContent: 'center', padding: 40 }}>
        <Spinner large />
      </div>
    )
  }

  return (
    <>
      <EndpointCard baseUrl={baseUrl} status={status} config={config} />
      <ConfigSection config={config} reload={reload} push={push} />
      <KeysSection keys={keys} status={status} config={config} reload={reload} push={push} />
      <ExamplesSection baseUrl={baseUrl} config={config} keys={keys} />
      <ReferenceSection config={config} />
      <TestConsole config={config} keys={keys} />
    </>
  )
}

