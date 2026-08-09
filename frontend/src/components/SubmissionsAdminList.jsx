import { useState, useEffect, useCallback } from 'react'
import { getAllSubmissions } from '../api'

const STATUS_LABEL = {
  pending:    'Pendiente',
  processing: 'En proceso',
  graded:     'Evaluado',
  rejected:   'Rechazado',
}
const STATUS_COLOR = {
  pending:    '#f59e0b',
  processing: '#3b82f6',
  graded:     '#22c55e',
  rejected:   '#ef4444',
}

function StatusBadge({ status }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: '4px',
      background: STATUS_COLOR[status] || '#6b7280',
      color: '#fff',
      fontSize: '0.82em',
      fontWeight: 600,
    }}>
      {STATUS_LABEL[status] || status}
    </span>
  )
}

function SubmissionImages({ token, submission, open }) {
  const [front, setFront] = useState(null)
  const [back, setBack]   = useState(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!open || loaded) return
    // Las imágenes del envío se sirven desde el endpoint de submissions
    fetchSubmissionImages(token, submission.evaluation_id).then(({ frontUrl, backUrl }) => {
      setFront(frontUrl)
      setBack(backUrl)
      setLoaded(true)
    })
  }, [open, loaded, token, submission.evaluation_id])

  if (!open) return null

  return (
    <div style={{ display: 'flex', gap: '1rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
      <div>
        <p style={{ margin: '0 0 4px', fontSize: '0.8em', color: '#666' }}>Frente</p>
        {front
          ? <img src={front} alt="frente" style={{ maxHeight: 200, borderRadius: 6, border: '1px solid #ddd' }} />
          : <span style={{ fontSize: '0.85em', color: '#999' }}>Cargando…</span>
        }
      </div>
      <div>
        <p style={{ margin: '0 0 4px', fontSize: '0.8em', color: '#666' }}>Reverso</p>
        {back
          ? <img src={back} alt="reverso" style={{ maxHeight: 200, borderRadius: 6, border: '1px solid #ddd' }} />
          : <span style={{ fontSize: '0.85em', color: '#999' }}>Cargando…</span>
        }
      </div>
    </div>
  )
}

async function fetchSubmissionImages(token, evaluationId) {
  const BASE = '/api/v3'
  const fetchBlob = async (side) => {
    const res = await fetch(`${BASE}/submissions/${evaluationId}/images/${side}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return null
    return URL.createObjectURL(await res.blob())
  }
  const [frontUrl, backUrl] = await Promise.all([fetchBlob('front'), fetchBlob('back')])
  return { frontUrl, backUrl }
}

function SubmissionRow({ token, submission }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <tr style={{ cursor: 'pointer' }} onClick={() => setExpanded(e => !e)}>
        <td style={{ fontFamily: 'monospace', fontSize: '0.78em' }}>
          {submission.evaluation_id.slice(0, 8)}…
        </td>
        <td style={{ fontFamily: 'monospace', fontSize: '0.78em' }}>
          {submission.user_id.slice(0, 8)}…
        </td>
        <td><StatusBadge status={submission.status} /></td>
        <td>
          {submission.image_quality_score != null
            ? `${(submission.image_quality_score * 100).toFixed(0)}%`
            : '—'}
        </td>
        <td style={{ fontSize: '0.82em' }}>
          {new Date(submission.received_at).toLocaleString()}
        </td>
        <td style={{ fontSize: '0.85em', color: '#2563eb' }}>
          {expanded ? '▲ cerrar' : '▼ ver imágenes'}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} style={{ background: '#f9fafb', padding: '0.75rem 1rem' }}>
            {submission.card_id && (
              <p style={{ margin: '0 0 6px', fontSize: '0.83em' }}>
                <strong>Carta asociada:</strong>{' '}
                <code>{submission.card_id}</code>
              </p>
            )}
            {submission.rejection_reason && (
              <p style={{ margin: '0 0 6px', fontSize: '0.83em', color: '#dc2626' }}>
                <strong>Motivo de rechazo:</strong> {submission.rejection_reason}
              </p>
            )}
            <SubmissionImages token={token} submission={submission} open={expanded} />
          </td>
        </tr>
      )}
    </>
  )
}

export default function SubmissionsAdminList({ token }) {
  const [submissions, setSubmissions] = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [filter, setFilter]           = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getAllSubmissions(token)
      setSubmissions(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { load() }, [load])

  const filtered = filter === 'all'
    ? submissions
    : submissions.filter(s => s.status === filter)

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Envíos para evaluación</h2>
        <button className="link-btn" onClick={load}>↻ Actualizar</button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {['all', 'pending', 'processing', 'graded', 'rejected'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              padding: '3px 12px',
              borderRadius: 4,
              border: '1px solid #d1d5db',
              background: filter === s ? '#2563eb' : '#fff',
              color: filter === s ? '#fff' : '#374151',
              cursor: 'pointer',
              fontSize: '0.85em',
            }}
          >
            {s === 'all' ? 'Todos' : STATUS_LABEL[s]}
            {s === 'all'
              ? ` (${submissions.length})`
              : ` (${submissions.filter(x => x.status === s).length})`}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      {loading ? (
        <p>Cargando envíos…</p>
      ) : filtered.length === 0 ? (
        <p style={{ color: '#6b7280' }}>No hay envíos{filter !== 'all' ? ` con estado "${STATUS_LABEL[filter]}"` : ''}.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
                <th style={{ padding: '8px 10px' }}>ID envío</th>
                <th style={{ padding: '8px 10px' }}>ID usuario</th>
                <th style={{ padding: '8px 10px' }}>Estado</th>
                <th style={{ padding: '8px 10px' }}>Calidad</th>
                <th style={{ padding: '8px 10px' }}>Recibido</th>
                <th style={{ padding: '8px 10px' }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <SubmissionRow key={s.evaluation_id} token={token} submission={s} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
