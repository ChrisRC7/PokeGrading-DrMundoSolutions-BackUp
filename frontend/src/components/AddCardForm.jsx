import { useState } from 'react'
import { addCard, ocrExtractCard } from '../api'

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'ja', label: 'Japanese (日本語)' },
  { value: 'es', label: 'Español' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
  { value: 'it', label: 'Italiano' },
  { value: 'pt', label: 'Português' },
  { value: 'ko', label: '한국어' },
  { value: 'zh', label: '中文' },
  { value: 'pl', label: 'Polski' },
  { value: 'nl', label: 'Nederlands' },
  { value: 'th', label: 'ภาษาไทย' },
]

const EMPTY_CARD = {
  set_name: '', card_number: '', edition: '', language: '', finish: '',
  name: '', rarity: '', pokemon_type: '', hp: '',
}

export default function AddCardForm({ token }) {
  const [step, setStep] = useState('form')   // 'form' | 'done'
  const [card, setCard] = useState(EMPTY_CARD)
  const [createdCard, setCreatedCard] = useState(null)
  const [frontFile, setFrontFile] = useState(null)   // imagen de frente (obligatoria) = OCR + referencia + hash
  const [backFile, setBackFile] = useState(null)     // reverso (opcional)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  // OCR scan state
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrResult, setOcrResult] = useState(null)   // { raw_text, detected } | { error }
  const [ocrFilled, setOcrFilled] = useState({})     // qué campos se rellenaron automáticamente

  const handleCardChange = (e) =>
    setCard((c) => ({ ...c, [e.target.name]: e.target.value }))

  // Imagen de frente: se guarda para enviarla al crear la carta Y se analiza con OCR
  // para pre-rellenar el formulario. Es la MISMA imagen que generará el pHash.
  const handleFrontSelect = async (e) => {
    const file = e.target.files[0] || null
    setFrontFile(file)
    if (!file) return
    setOcrLoading(true)
    setOcrResult(null)
    setOcrFilled({})
    try {
      const data = await ocrExtractCard(token, file)
      setOcrResult(data)
      const { name, hp, card_number } = data.detected
      const filled = {}
      const patch = {}
      if (name)        { patch.name = name;               filled.name = true }
      if (hp != null)  { patch.hp = String(hp);           filled.hp = true }
      if (card_number) { patch.card_number = card_number; filled.card_number = true }
      setCard(c => ({ ...c, ...patch }))
      setOcrFilled(filled)
    } catch (err) {
      setOcrResult({ error: err.message })
    } finally {
      setOcrLoading(false)
    }
  }

  // Crear la carta: envía los campos + imagen de frente (obligatoria) + reverso (opcional).
  const handleAddCard = async (e) => {
    e.preventDefault()
    setError(null)
    if (!frontFile) {
      setError('La imagen de frente es obligatoria: se usa como referencia y para la búsqueda por huella (pHash).')
      return
    }
    setLoading(true)
    try {
      const payload = { ...card }
      if (!payload.rarity) delete payload.rarity
      if (!payload.pokemon_type) delete payload.pokemon_type
      if (!payload.hp) delete payload.hp
      else payload.hp = Number(payload.hp)
      const data = await addCard(token, payload, frontFile, backFile)
      setCreatedCard(data)
      setStep('done')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setStep('form')
    setCard(EMPTY_CARD)
    setCreatedCard(null)
    setFrontFile(null)
    setBackFile(null)
    setError(null)
    setOcrResult(null)
    setOcrFilled({})
  }

  // ── Confirmación final ──
  if (step === 'done') {
    return (
      <div className="card">
        <div className="alert success">
          <p><strong>¡Carta agregada exitosamente!</strong></p>
          <p>{createdCard.name} — {createdCard.identity?.set_name} #{createdCard.identity?.card_number}</p>
          <p>Estado: <strong>{createdCard.status}</strong> | Versión: {createdCard.version}</p>
          <p>✓ Imagen de frente guardada como referencia (huella pHash generada).</p>
          {createdCard.has_image_back && <p>✓ Imagen de reverso guardada.</p>}
        </div>
        <button onClick={handleReset}>Agregar otra carta</button>
      </div>
    )
  }

  // ── Formulario (un solo paso) ──
  return (
    <div className="card">
      <h2>Agregar carta al catálogo</h2>

      {/* ── Imagen de frente (obligatoria) + escaneo OCR ── */}
      <div className="ocr-scan-panel">
        <div className="ocr-scan-header">
          <span>📷 Imagen de frente (obligatoria)</span>
          <span className="ocr-scan-hint">
            Al seleccionarla se rellenan los campos por OCR y esta misma imagen se guarda
            como referencia y genera la huella (pHash) para la búsqueda.
          </span>
        </div>
        <label className="ocr-scan-label">
          <input
            type="file"
            accept="image/jpeg,image/png"
            onChange={handleFrontSelect}
            disabled={ocrLoading}
          />
          {ocrLoading && <span className="ocr-scanning">⏳ Analizando imagen…</span>}
        </label>
        {frontFile && <p style={{ fontSize: '0.85em', color: '#2a7' }}>✓ {frontFile.name}</p>}

        {ocrResult && !ocrResult.error && (
          <div className="ocr-scan-result">
            <div className="ocr-scan-raw">
              <span>🔍 Texto extraído:</span>
              <code>{ocrResult.raw_text || '(sin texto reconocible)'}</code>
            </div>
            <div className="ocr-scan-fields">
              {ocrResult.detected.name        && <span className="ocr-tag">nombre: <strong>{ocrResult.detected.name}</strong></span>}
              {ocrResult.detected.hp != null  && <span className="ocr-tag">HP: <strong>{ocrResult.detected.hp}</strong></span>}
              {ocrResult.detected.card_number && <span className="ocr-tag">N°: <strong>{ocrResult.detected.card_number}</strong></span>}
              {!ocrResult.detected.name && ocrResult.detected.hp == null && !ocrResult.detected.card_number && (
                <span className="ocr-tag ocr-tag-warn">No se detectaron campos — rellena manualmente</span>
              )}
            </div>
          </div>
        )}
        {ocrResult?.error && (
          <p className="ocr-scan-error">⚠️ {ocrResult.error}</p>
        )}
      </div>

      <form onSubmit={handleAddCard}>
        <fieldset>
          <legend>Identidad de la carta (requeridos)</legend>
          <label>Nombre del set
            <input name="set_name" value={card.set_name} onChange={handleCardChange} required />
          </label>
          <label>Número de carta
            <input name="card_number" value={card.card_number} onChange={handleCardChange} required />
            {ocrFilled.card_number && <span className="ocr-autofill-badge">🤖 OCR</span>}
          </label>
          <label>Edición
            <input name="edition" value={card.edition} onChange={handleCardChange} required />
          </label>
          <label>Idioma
            <select name="language" value={card.language} onChange={handleCardChange} required>
              <option value="">— Seleccionar —</option>
              {LANGUAGES.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>Acabado (finish)
            <input name="finish" value={card.finish} onChange={handleCardChange} required />
          </label>
        </fieldset>

        <fieldset>
          <legend>Datos generales</legend>
          <label>Nombre de la carta
            <input name="name" value={card.name} onChange={handleCardChange} required />
            {ocrFilled.name && <span className="ocr-autofill-badge">🤖 OCR</span>}
          </label>
          <label>Rareza (opcional)
            <input name="rarity" value={card.rarity} onChange={handleCardChange} />
          </label>
          <label>Tipo (opcional)
            <input name="pokemon_type" value={card.pokemon_type} onChange={handleCardChange} />
          </label>
          <label>HP (opcional)
            <input name="hp" type="number" min="0" value={card.hp} onChange={handleCardChange} />
            {ocrFilled.hp && <span className="ocr-autofill-badge">🤖 OCR</span>}
          </label>
        </fieldset>

        <fieldset>
          <legend>Imagen de reverso (opcional)</legend>
          <label>Reverso de la carta
            <input
              type="file"
              accept="image/jpeg,image/png"
              onChange={(e) => setBackFile(e.target.files[0] || null)}
            />
          </label>
        </fieldset>

        <button type="submit" disabled={loading || ocrLoading}>
          {loading ? 'Creando…' : 'Crear carta'}
        </button>
      </form>
      {error && <div className="alert error">{error}</div>}
    </div>
  )
}
