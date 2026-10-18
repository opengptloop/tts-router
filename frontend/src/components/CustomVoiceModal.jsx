import { useMemo, useState } from 'react'
import { Upload } from 'lucide-react'
import { api } from '../api.js'
import { Field, Modal, Spinner } from './ui.jsx'

export function CustomVoiceModal({ engine, voices, onClose, onUploaded }) {
  const [name, setName] = useState('')
  const [language, setLanguage] = useState('a')
  const [referenceText, setReferenceText] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const type = engine.custom_voice_types?.[0]
  const languages = useMemo(() => {
    const map = new Map()
    for (const voice of voices || []) {
      if (voice.lang_code && !map.has(voice.lang_code)) {
        map.set(voice.lang_code, {
          code: voice.lang_code,
          label: `${voice.extra?.flag || ''} ${voice.language}`.trim(),
        })
      }
    }
    return [...map.values()]
  }, [voices])

  const needsLanguage = engine.id === 'kokoro'
  const needsReferenceText = engine.id === 'kitten'

  const submit = async (event) => {
    event.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Give the voice a name.')
    if (!files.length) return setError('Choose at least one file.')
    setBusy(true)
    try {
      const form = new FormData()
      form.append('engine', engine.id)
      form.append('name', name.trim())
      if (needsLanguage) form.append('language', language)
      if (referenceText.trim()) form.append('reference_text', referenceText.trim())
      for (const file of files) form.append('files', file)
      const data = await api('/api/voices/custom', { method: 'POST', body: form, isForm: true })
      onUploaded(data.voice)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`Add custom voice · ${engine.name}`} onClose={onClose}>
      <form onSubmit={submit}>
        <p className="muted small" style={{ marginTop: 0 }}>
          {type?.help}
        </p>

        <Field label="Voice name">
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My voice"
            autoFocus
          />
        </Field>

        {needsLanguage && (
          <Field
            label="Language"
            help="The language pipeline used to phonemize text before synthesis."
          >
            <select className="select" value={language} onChange={(e) => setLanguage(e.target.value)}>
              {(languages.length ? languages : [{ code: 'a', label: 'American English' }]).map(
                (option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ),
              )}
            </select>
          </Field>
        )}

        {needsReferenceText && (
          <Field
            label="Reference transcript (optional)"
            help="What is said in the clip. Leave empty to auto-transcribe with Whisper."
          >
            <textarea
              className="input"
              style={{ minHeight: 70 }}
              value={referenceText}
              onChange={(e) => setReferenceText(e.target.value)}
              placeholder="Transcript of the reference audio…"
            />
          </Field>
        )}

        <Field label={type?.label || 'Files'} help={type?.accept ? `Accepted: ${type.accept}` : undefined}>
          <input
            className="input"
            type="file"
            accept={type?.accept}
            multiple={engine.id === 'piper'}
            onChange={(e) => setFiles([...e.target.files])}
          />
        </Field>

        {error && (
          <div className="badge danger" style={{ display: 'block', marginBottom: 12, padding: 9 }}>
            {error}
          </div>
        )}

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? <Spinner /> : <Upload size={15} />}
            {busy ? 'Uploading…' : 'Add voice'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
