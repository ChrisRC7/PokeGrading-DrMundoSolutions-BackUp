const BASE = '/api/v3'

export async function registerUser({ email, password, alias, accept_disclosure, country, preferred_language }) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, alias, accept_disclosure, country, preferred_language }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al registrar')
  return data
}

export async function loginUser({ email, password }) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Credenciales inválidas')
  return data
}

export async function getCards(token) {
  const res = await fetch(`${BASE}/catalog/cards`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al obtener cartas')
  return data
}

export async function reviewCard(token, cardId, newStatus) {
  const res = await fetch(`${BASE}/catalog/cards/${cardId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ status: newStatus }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al actualizar carta')
  return data
}

/**
 * Crea una carta en el catálogo. La imagen de frente es OBLIGATORIA: se guarda
 * como referencia y genera el pHash para la búsqueda rápida. El reverso es opcional.
 * Petición multipart/form-data.
 */
export async function addCard(token, cardData, frontFile, backFile = null) {
  const form = new FormData()
  for (const [key, value] of Object.entries(cardData)) {
    if (value !== undefined && value !== null && value !== '') {
      form.append(key, value)
    }
  }
  form.append('image_front', frontFile)
  if (backFile) form.append('image_back', backFile)

  const res = await fetch(`${BASE}/catalog/cards`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al agregar carta')
  return data
}

export async function uploadCardImage(token, cardId, side, file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/catalog/cards/${cardId}/images/${side}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || `Error al subir imagen (${side})`)
  return data
}

export async function fetchCardImageBlob(token, cardId, side) {
  const res = await fetch(`${BASE}/catalog/cards/${cardId}/images/${side}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return null
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export async function submitCardForEvaluation(token, frontFile, backFile, cardId = null) {
  const form = new FormData()
  form.append('image_front', frontFile)
  form.append('image_back', backFile)
  if (cardId) form.append('card_id', cardId)
  const res = await fetch(`${BASE}/submissions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al enviar carta')
  return data
}

export async function getSubmissionStatus(token, evaluationId) {
  const res = await fetch(`${BASE}/submissions/${evaluationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al consultar estado')
  return data
}

/**
 * Sprint 4 — Preprocesar carta: corrige perspectiva, recorta, normaliza color
 * y segmenta en 4 regiones (centering, corners, edges, surface).
 * Devuelve { status: "preprocessed" | "manual_review" | "needs_recapture", reason }.
 */
export async function preprocessSubmission(token, evaluationId) {
  const res = await fetch(`${BASE}/submissions/${evaluationId}/preprocess`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al preprocesar la carta')
  return data
}

/**
 * Sprint 4 — Calificar carta: grado estimado por pHash sobre las 4 regiones.
 * Es idempotente: reintentar el mismo envío devuelve la misma evaluación.
 * Devuelve { status: "graded" | "manual_review", final_grade, uncertainty,
 *   subgrades:[{region, score, hamming_distance, confidence}], baseline_ref,
 *   algorithm_version }.
 */
export async function gradeSubmission(token, evaluationId) {
  const res = await fetch(`${BASE}/submissions/${evaluationId}/grade`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al calificar la carta')
  return data
}

export async function getAllSubmissions(token) {
  const res = await fetch(`${BASE}/submissions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al obtener envíos')
  return data
}

/**
 * US-004: Búsqueda rápida de carta por imagen.
 * @param {string} token
 * @param {File} frontFile  Imagen de frente (JPEG/PNG)
 * @param {string|null} queryHint  Texto opcional para modo dev (reemplaza ML)
 * @returns {{ candidates: Array, auto_accepted: boolean, total: number }}
 */
export async function quickSearchCard(token, frontFile, queryHint = null) {
  const form = new FormData()
  form.append('image_front', frontFile)
  if (queryHint) form.append('q', queryHint)

  const res = await fetch(`${BASE}/search/quick`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })

  if (res.status === 404) {
    const data = await res.json()
    const detail = data.detail
    const ocrText = detail && typeof detail === 'object' ? detail.ocr_text : null
    const focusedQ = detail && typeof detail === 'object' ? detail.focused_q : null
    return { candidates: [], auto_accepted: false, total: 0, notFound: true, ocr_text: ocrText, focused_q: focusedQ }
  }
  if (res.status === 422) return { candidates: [], auto_accepted: false, total: 0, notIdentifiable: true }
  if (!res.ok) {
    const data = await res.json()
    throw new Error(data.detail || 'Error en búsqueda rápida')
  }
  return res.json()
}

export async function ocrExtractCard(token, frontFile) {
  const form = new FormData()
  form.append('image_front', frontFile)
  const res = await fetch(`${BASE}/search/ocr-extract`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error al extraer texto de la imagen')
  return data
}
