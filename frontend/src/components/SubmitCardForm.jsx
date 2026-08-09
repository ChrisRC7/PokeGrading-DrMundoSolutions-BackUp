import { useState } from 'react'
import { submitCardForEvaluation, getSubmissionStatus, quickSearchCard, preprocessSubmission, gradeSubmission } from '../api'

// Etiquetas legibles por región para el desglose de subgrades (Sprint 4).
const REGION_LABELS = {
  centering: 'Centrado',
  corners: 'Esquinas',
  edges: 'Bordes',
  surface: 'Superficie',
}

export default function SubmitCardForm({ token }) {
  const [frontFile, setFrontFile] = useState(null)
  const [backFile, setBackFile]   = useState(null)
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState('')

  // US-004: búsqueda rápida
  const [searching, setSearching]         = useState(false)
  const [candidates, setCandidates]       = useState(null)   // null = sin búsqueda aún
  const [searchMsg, setSearchMsg]         = useState('')
  const [selectedCard, setSelectedCard]   = useState(null)   // candidato elegido
  const [queryHint, setQueryHint]         = useState('')     // búsqueda manual por texto
  const [debugResponse, setDebugResponse] = useState(null)  // respuesta cruda del API (dev)
  const [imageQualityScore, setImageQualityScore] = useState(null) // calidad de la foto subida

  // Estado del envío consultado
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusData, setStatusData]       = useState(null)

  // Sprint 4 — Calificación (preprocesar → calificar)
  const [grading, setGrading]         = useState(false)
  const [gradeResult, setGradeResult] = useState(null)   // EvaluationResponse
  const [gradeMsg, setGradeMsg]       = useState('')     // mensaje de ramas alternas

  // ── Cuando se elige la imagen de frente, lanzar búsqueda automática ────────
  const runSearch = async (file, q) => {
    setSearching(true)
    setCandidates(null)
    setSelectedCard(null)
    setSearchMsg('')
    setImageQualityScore(null)
    try {
      const res = await quickSearchCard(token, file, q || null)
      setDebugResponse(res)
      // Guardar el score de calidad de la imagen (viene del backend en todos los casos)
      if (res.image_quality_score != null) setImageQualityScore(res.image_quality_score)
      else if (res.notFound && res.image_quality_score != null) setImageQualityScore(res.image_quality_score)
      if (res.notIdentifiable) {
        setSearchMsg('No se pudo identificar la carta automáticamente. Escribe el nombre o número para buscarla.')
        setCandidates([])
      } else if (res.notFound || res.total === 0) {
        setSearchMsg('No se encontró ninguna carta similar en el catálogo. Puedes enviarla sin identificar.')
        setCandidates([])
      } else {
        setCandidates(res.candidates)
        if (res.auto_accepted && res.candidates.length > 0) {
          setSelectedCard(res.candidates[0])
          setSearchMsg(`Coincidencia automática: "${res.candidates[0].name}" (${(res.candidates[0].confidence_score * 100).toFixed(0)}% confianza) — puedes elegir otra abajo`)
        } else {
          setSearchMsg(`Se encontraron ${res.total} posible${res.total > 1 ? 's' : ''} coincidencia${res.total > 1 ? 's' : ''}. Elige la correcta:`)
        }
      }
    } catch (err) {
      setDebugResponse({ error: err.message })
      setSearchMsg('Error en la búsqueda. Puedes continuar manualmente.')
      setCandidates([])
    } finally {
      setSearching(false)
    }
  }

  const handleFrontChange = async (e) => {
    const file = e.target.files[0] || null
    setFrontFile(file)
    setQueryHint('')
    setImageQualityScore(null)
    if (!file) {
      setCandidates(null); setSelectedCard(null); setSearchMsg(''); setDebugResponse(null); return
    }
    await runSearch(file, '')
  }

  const handleManualSearch = async (e) => {
    e.preventDefault()
    if (!frontFile || !queryHint.trim()) return
    await runSearch(frontFile, queryHint.trim())
  }

  const handleSelectCandidate = (candidate) => {
    setSelectedCard(candidate)
    setSearchMsg(`Carta seleccionada: "${candidate.name}" · ${candidate.set_name} · ${candidate.card_number}`)
  }

  const handleClearSelection = () => {
    setSelectedCard(null)
    setCandidates(null)
    setFrontFile(null)
    setQueryHint('')
    setSearchMsg('')
    setImageQualityScore(null)
  }

  // ── Envío ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setResult(null)
    setStatusData(null)

    if (!frontFile || !backFile) {
      setError('Debes seleccionar la imagen de frente y de reverso.')
      return
    }

    setLoading(true)
    try {
      const data = await submitCardForEvaluation(
        token,
        frontFile,
        backFile,
        selectedCard?.candidate_card_id ?? null,
      )
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleCheckStatus = async () => {
    if (!result?.evaluation_id) return
    setStatusLoading(true)
    try {
      const data = await getSubmissionStatus(token, result.evaluation_id)
      setStatusData(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setStatusLoading(false)
    }
  }

  // ── Calificar carta: PRIMERO preprocesa, LUEGO califica (Sprint 4) ─────────
  const handleGrade = async () => {
    if (!result?.evaluation_id) return
    setGrading(true)
    setGradeResult(null)
    setGradeMsg('')
    setError('')
    try {
      // 1) Preprocesar: corrige perspectiva, recorta, normaliza y segmenta.
      const pre = await preprocessSubmission(token, result.evaluation_id)
      if (pre.status === 'needs_recapture') {
        setGradeMsg('⚠️ La imagen tiene distorsiones imposibles de corregir. Vuelve a capturar la carta.')
        return
      }
      if (pre.status === 'manual_review') {
        setGradeMsg('⚠️ No se pudo aislar la carta del fondo: se derivó a calificación manual.')
        return
      }
      // 2) Calificar: solo si el preprocesamiento fue exitoso (PREPROCESSED).
      const grade = await gradeSubmission(token, result.evaluation_id)
      setGradeResult(grade)
      if (grade.status === 'manual_review') {
        setGradeMsg('⚠️ La carta se derivó a revisión humana (insumos insuficientes o resultado incoherente).')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setGrading(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="card">
      <h2>Enviar carta para evaluación</h2>
      <p className="hint">
        Sube la foto de frente: el sistema buscará automáticamente la carta en el catálogo.
        Formatos aceptados: JPEG, PNG. Máximo 10 MB por imagen.
      </p>

      <form onSubmit={handleSubmit}>
        {/* ── Imagen de frente ── */}
        <div className="form-group">
          <label>Imagen de frente *</label>
          <input
            type="file"
            accept="image/jpeg,image/png"
            onChange={handleFrontChange}
          />
          {frontFile && (
            <span className="file-info">{frontFile.name} ({(frontFile.size / 1024).toFixed(0)} KB)</span>
          )}
        </div>

        {/* ── Calidad de la imagen de frente ── */}
        {imageQualityScore != null && (
          <div className="quality-row">
            <span className="quality-label">Calidad de la foto:</span>
            <QualityBar value={imageQualityScore} />
          </div>
        )}

        {/* ── Búsqueda automática ── */}
        {searching && (
          <div className="search-status searching">
            🔍 Buscando carta en el catálogo…
          </div>
        )}

        {!searching && searchMsg && (
          <div className={`search-status ${selectedCard ? 'match-found' : candidates?.length === 0 ? 'no-match' : candidates?.length > 0 ? 'has-candidates' : ''}`}>
            {selectedCard ? '✅' : candidates?.length === 0 ? '⚠️' : '🔎'} {searchMsg}
          </div>
        )}

        {/* ── Búsqueda manual por texto (cuando no hubo identificación automática) ── */}
        {!searching && candidates !== null && candidates.length === 0 && !selectedCard && frontFile && (
          <div className="manual-search">
            <label>Buscar por nombre o número de carta</label>
            <div className="manual-search-row">
              <input
                type="text"
                placeholder="Ej: Pikachu, 025/185, Charizard V…"
                value={queryHint}
                onChange={(e) => setQueryHint(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleManualSearch(e)}
              />
              <button
                type="button"
                className="btn-search"
                onClick={handleManualSearch}
                disabled={!queryHint.trim()}
              >
                Buscar
              </button>
            </div>
            <span className="file-info">
              Si no encuentras la carta en el catálogo, puedes enviarla igual sin identificar.
            </span>
          </div>
        )}

        {/* ── Top 3 candidatos — siempre visibles, seleccionado resaltado ── */}
        {!searching && candidates && candidates.length > 0 && (
          <div className="candidates-panel">
            <div className="candidates-header">
              <span>Top {candidates.length} candidato{candidates.length > 1 ? 's' : ''}</span>
              {selectedCard && <span className="candidates-selected-hint">✅ Seleccionado — haz clic en otro para cambiar</span>}
            </div>
            {candidates.map((c) => {
              const isSelected = selectedCard?.candidate_card_id === c.candidate_card_id
              return (
                <button
                  key={c.candidate_card_id}
                  type="button"
                  className={`candidate-card${isSelected ? ' candidate-selected' : ''}`}
                  onClick={() => handleSelectCandidate(c)}
                >
                  <div className="candidate-rank">{isSelected ? '✅' : `#${c.rank}`}</div>
                  <div className="candidate-info">
                    <strong>{c.name}</strong>
                    <span>{c.set_name} · {c.card_number}</span>
                    {c.language && <span>Idioma: {c.language.toUpperCase()}</span>}
                    {c.rarity && <span>Rareza: {c.rarity}</span>}
                    {c.hp && <span>HP: {c.hp}</span>}
                  </div>
                  <div className="candidate-confidence">
                    <ConfidenceBar value={c.confidence_score} />
                    {(c.confidence_score * 100).toFixed(0)}%
                  </div>
                </button>
              )
            })}
            <button type="button" className="link-btn" onClick={() => setSelectedCard(null)}>
              Ninguna coincide — continuar sin identificar
            </button>
          </div>
        )}

        {/* ── Imagen de reverso ── */}
        <div className="form-group">
          <label>Imagen de reverso *</label>
          <input
            type="file"
            accept="image/jpeg,image/png"
            onChange={(e) => setBackFile(e.target.files[0] || null)}
          />
          {backFile && (
            <span className="file-info">{backFile.name} ({(backFile.size / 1024).toFixed(0)} KB)</span>
          )}
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={loading || searching}>
          {loading ? 'Enviando…' : 'Enviar para evaluación'}
        </button>
      </form>

      {/* ── Panel de depuración (dev) ── */}
      {debugResponse && (
        <details className="debug-panel">
          <summary>🛠️ Respuesta del API (modo desarrollo)</summary>
          <div className="debug-content">
            {debugResponse.error ? (
              <p className="debug-error">Error: {debugResponse.error}</p>
            ) : debugResponse.notIdentifiable ? (
              <>
                <div className="debug-row ocr-row">
                  <span>🔍 Texto extraído por OCR</span>
                  <code className="ocr-empty">(ninguno — imagen ilegible)</code>
                </div>
                <p className="debug-hint">
                  ⚠️ <strong>422</strong> — EasyOCR no pudo extraer texto legible de la imagen.<br />
                  Asegúrate de que la imagen muestre claramente el nombre y número de la carta,
                  o usa el campo de búsqueda manual.
                </p>
              </>
            ) : debugResponse.notFound ? (
              <>
                <div className="debug-row ocr-row">
                  <span>🔍 Texto extraído por OCR</span>
                  {debugResponse.ocr_text
                    ? <code className="ocr-found">{debugResponse.ocr_text}</code>
                    : <code className="ocr-manual">(búsqueda manual — OCR omitido)</code>}
                </div>
                {debugResponse.focused_q && (
                  <div className="debug-row ocr-row" style={{background:'#fef9c3',borderColor:'#fde047'}}>
                    <span style={{color:'#854d0e'}}>🎯 Query usada para buscar</span>
                    <code style={{background:'#fef08a',color:'#713f12'}}>{debugResponse.focused_q}</code>
                  </div>
                )}
                <p className="debug-hint">
                  ⚠️ <strong>404</strong> — no hay cartas en el catálogo que coincidan con "<em>{debugResponse.focused_q || debugResponse.ocr_text || 'la búsqueda'}</em>".<br />
                  Prueba con otro nombre o número de carta.
                </p>
              </>
            ) : (
              <>
                <div className="debug-row ocr-row">
                  <span>🔍 Texto extraído por OCR</span>
                  {debugResponse.ocr_text
                    ? <code className="ocr-found">{debugResponse.ocr_text}</code>
                    : <code className="ocr-manual">(búsqueda manual — OCR omitido)</code>}
                </div>
                <div className="debug-row"><span>auto_accepted</span><code>{String(debugResponse.auto_accepted)}</code></div>
                <div className="debug-row"><span>total candidatos</span><code>{debugResponse.total}</code></div>
                {debugResponse.candidates?.map((c, i) => (
                  <div key={i} className="debug-candidate">
                    <div className="debug-row"><span>Rank</span><code>#{c.rank}</code></div>
                    <div className="debug-row"><span>ID</span><code>{c.candidate_card_id}</code></div>
                    <div className="debug-row"><span>Nombre</span><code>{c.name}</code></div>
                    <div className="debug-row"><span>Set</span><code>{c.set_name}</code></div>
                    <div className="debug-row"><span>Número</span><code>{c.card_number}</code></div>
                    <div className="debug-row"><span>Idioma</span><code>{c.language}</code></div>
                    <div className="debug-row"><span>Rareza</span><code>{c.rarity ?? '—'}</code></div>
                    <div className="debug-row"><span>HP</span><code>{c.hp ?? '—'}</code></div>
                    <div className="debug-row"><span>Tipo</span><code>{c.pokemon_type ?? '—'}</code></div>
                    <div className="debug-row"><span>Confianza</span><code>{(c.confidence_score * 100).toFixed(1)}%</code></div>
                  </div>
                ))}
              </>
            )}
          </div>
        </details>
      )}

      {/* ── Resultado del envío ── */}
      {result && (
        <div className="success-box">
          <h3>✅ Envío recibido</h3>
          <table className="info-table">
            <tbody>
              <tr><td><strong>ID de evaluación</strong></td><td><code>{result.evaluation_id}</code></td></tr>
              <tr><td><strong>Estado</strong></td><td><StatusBadge status={result.status} /></td></tr>
              <tr><td><strong>Recibido</strong></td><td>{new Date(result.received_at).toLocaleString()}</td></tr>
              {result.image_quality_score != null && (
                <tr>
                  <td><strong>Calidad de imagen</strong></td>
                  <td>
                    <QualityBar value={result.image_quality_score} />
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.75rem', alignItems: 'center' }}>
            {/* Botón principal de Sprint 4: preprocesa y luego califica */}
            <button onClick={handleGrade} disabled={grading}>
              {grading ? 'Calificando…' : '⭐ Calificar carta'}
            </button>
            <button className="link-btn" onClick={handleCheckStatus} disabled={statusLoading}>
              {statusLoading ? 'Consultando…' : '↻ Actualizar estado'}
            </button>
          </div>

          {grading && (
            <p className="hint" style={{ marginTop: '0.5rem' }}>
              Preprocesando la imagen (perspectiva, recorte, color, 4 regiones) y calculando el grado…
            </p>
          )}

          {gradeMsg && <p className="error" style={{ marginTop: '0.75rem' }}>{gradeMsg}</p>}

          {gradeResult && gradeResult.status === 'graded' && (
            <GradeResult grade={gradeResult} />
          )}

          {statusData && (
            <div style={{ marginTop: '0.75rem' }}>
              <strong>Estado actual:</strong> <StatusBadge status={statusData.status} />
              {statusData.image_quality_score != null && (
                <div style={{ marginTop: '0.5rem' }}>
                  <strong>Calidad de imagen:</strong>
                  <QualityBar value={statusData.image_quality_score} />
                </div>
              )}
              {statusData.rejection_reason && (
                <p className="error">Motivo de rechazo: {statusData.rejection_reason}</p>
              )}
            </div>
          )}

          <button
            style={{ marginTop: '1rem' }}
            onClick={() => {
              setResult(null); setStatusData(null)
              setFrontFile(null); setBackFile(null)
              setCandidates(null); setSelectedCard(null); setSearchMsg(''); setQueryHint('')
              setImageQualityScore(null)
              setGradeResult(null); setGradeMsg('')
            }}
          >
            Nuevo envío
          </button>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const colors = {
    pending: '#f59e0b', processing: '#3b82f6', preprocessed: '#0ea5e9',
    graded: '#22c55e', rejected: '#ef4444', manual_review: '#a855f7', needs_recapture: '#f97316',
  }
  const labels = {
    pending: 'Pendiente', processing: 'En proceso', preprocessed: 'Preprocesada',
    graded: 'Evaluado', rejected: 'Rechazado', manual_review: 'Revisión manual', needs_recapture: 'Recapturar',
  }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: '4px',
      background: colors[status] || '#6b7280', color: '#fff', fontSize: '0.85em', fontWeight: 600,
    }}>
      {labels[status] || status}
    </span>
  )
}

// Sprint 4 — Muestra el grado estimado: grado final ± banda y los 4 subgrades.
function GradeResult({ grade }) {
  const gradeColor = (g) => (g >= 8 ? '#22c55e' : g >= 6 ? '#f59e0b' : '#ef4444')
  return (
    <div className="success-box" style={{ marginTop: '1rem', borderColor: '#22c55e' }}>
      <h3>⭐ Grado estimado</h3>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', margin: '0.5rem 0' }}>
        <span style={{ fontSize: '2.5rem', fontWeight: 800, color: gradeColor(grade.final_grade) }}>
          {grade.final_grade?.toFixed(1)}
        </span>
        <span style={{ fontSize: '1.1rem', color: '#6b7280' }}>/ 10.0</span>
        {grade.uncertainty != null && (
          <span style={{ fontSize: '1rem', color: '#6b7280' }}>± {grade.uncertainty.toFixed(1)}</span>
        )}
      </div>

      <table className="info-table">
        <tbody>
          {grade.subgrades?.map((sg) => (
            <tr key={sg.region}>
              <td><strong>{REGION_LABELS[sg.region] || sg.region}</strong></td>
              <td>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{ width: '120px', height: '8px', background: '#e5e7eb', borderRadius: '4px' }}>
                    <div style={{ width: `${(sg.score / 10) * 100}%`, height: '100%', background: gradeColor(sg.score), borderRadius: '4px' }} />
                  </div>
                  <span style={{ fontWeight: 700, color: gradeColor(sg.score), minWidth: '2.5rem' }}>
                    {sg.score.toFixed(1)}
                  </span>
                </div>
              </td>
            </tr>
          ))}
          <tr>
            <td><strong>Baseline</strong></td>
            <td><code>{grade.baseline_ref || '—'}</code></td>
          </tr>
          <tr>
            <td><strong>Versión del algoritmo</strong></td>
            <td><code>{grade.algorithm_version}</code></td>
          </tr>
        </tbody>
      </table>
      <p className="hint" style={{ marginTop: '0.5rem' }}>
        El grado final nunca supera el subgrade más bajo + 0.5. Es una estimación informativa,
        no reemplaza el grading profesional (PSA, BGS, CGC).
      </p>
    </div>
  )
}

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{ width: '80px', height: '6px', background: '#e5e7eb', borderRadius: '3px', marginBottom: '2px' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '3px' }} />
    </div>
  )
}

function QualityBar({ value }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#f59e0b' : '#ef4444'
  const label = pct >= 80 ? 'Buena' : pct >= 60 ? 'Aceptable' : 'Baja'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
      <div style={{ width: '120px', height: '8px', background: '#e5e7eb', borderRadius: '4px', flexShrink: 0 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '4px', transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontWeight: 700, color, minWidth: '2.5rem' }}>{pct}%</span>
      <span style={{ fontSize: '0.8em', color: '#6b7280' }}>{label}</span>
    </div>
  )
}

