import { useState, useEffect, useCallback } from 'react'
import { getCards, reviewCard, fetchCardImageBlob } from '../api'

const STATUS_LABEL = {
  pending: 'Pendiente',
  active: 'Aprobada',
  retired: 'Denegada',
}

const STATUS_CLASS = {
  pending: 'badge badge-pending',
  active: 'badge badge-active',
  retired: 'badge badge-retired',
}

function CardImages({ token, card }) {
  const [urls, setUrls] = useState({ front: null, back: null })
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)

  const hasAny = card.has_image_front || card.has_image_back

  const handleToggle = async () => {
    if (!visible && !urls.front && !urls.back) {
      setLoading(true)
      const [front, back] = await Promise.all([
        card.has_image_front ? fetchCardImageBlob(token, card.card_id, 'front') : Promise.resolve(null),
        card.has_image_back  ? fetchCardImageBlob(token, card.card_id, 'back')  : Promise.resolve(null),
      ])
      setUrls({ front, back })
      setLoading(false)
    }
    setVisible((v) => !v)
  }

  if (!hasAny) return null

  return (
    <div style={{ marginTop: '0.5rem' }}>
      <button
        className="link-btn"
        style={{ fontSize: '0.85em' }}
        onClick={handleToggle}
        disabled={loading}
      >
        {loading ? 'Cargando imágenes…' : visible ? '▲ Ocultar imágenes' : '▼ Ver imágenes de referencia'}
      </button>
      {visible && (
        <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
          {urls.front && (
            <div style={{ textAlign: 'center' }}>
              <p style={{ fontSize: '0.75em', margin: '0 0 4px' }}>Frente</p>
              <img
                src={urls.front}
                alt="Frente de la carta"
                style={{ maxWidth: '160px', maxHeight: '220px', borderRadius: '6px', border: '1px solid #ddd' }}
              />
            </div>
          )}
          {urls.back && (
            <div style={{ textAlign: 'center' }}>
              <p style={{ fontSize: '0.75em', margin: '0 0 4px' }}>Reverso</p>
              <img
                src={urls.back}
                alt="Reverso de la carta"
                style={{ maxWidth: '160px', maxHeight: '220px', borderRadius: '6px', border: '1px solid #ddd' }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function CardReviewList({ token }) {
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(null) // card_id being acted on

  const fetchCards = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getCards(token)
      setCards(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    fetchCards()
  }, [fetchCards])

  const handleReview = async (cardId, newStatus) => {
    setActionLoading(cardId)
    try {
      const updated = await reviewCard(token, cardId, newStatus)
      setCards((prev) =>
        prev.map((c) => (c.card_id === updated.card_id ? updated : c))
      )
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) return <div className="card"><p>Cargando cartas…</p></div>
  if (error) return <div className="card"><div className="alert error">{error}</div></div>

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Revisión de cartas</h2>
        <button className="link-btn" onClick={fetchCards}>Actualizar</button>
      </div>

      {cards.length === 0 ? (
        <p className="hint">No hay cartas registradas aún.</p>
      ) : (
        <div className="card-list">
          {cards.map((card) => (
            <div key={card.card_id} className="card-item">
              <div className="card-item-header">
                <strong>{card.name}</strong>
                <span className={STATUS_CLASS[card.status] ?? 'badge'}>
                  {STATUS_LABEL[card.status] ?? card.status}
                </span>
              </div>
              <div className="card-item-meta">
                {card.identity.set_name} · #{card.identity.card_number} · {card.identity.edition} · {card.identity.language} · {card.identity.finish}
              </div>
              {card.description && (
                <div className="card-item-desc">{card.description}</div>
              )}
              <CardImages token={token} card={card} />
              <div className="card-item-actions">
                <button
                  className="btn-approve"
                  disabled={card.status === 'active' || actionLoading === card.card_id}
                  onClick={() => handleReview(card.card_id, 'active')}
                >
                  Aprobar
                </button>
                <button
                  className="btn-deny"
                  disabled={card.status === 'retired' || actionLoading === card.card_id}
                  onClick={() => handleReview(card.card_id, 'retired')}
                >
                  Denegar
                </button>
                <button
                  className="btn-pending"
                  disabled={card.status === 'pending' || actionLoading === card.card_id}
                  onClick={() => handleReview(card.card_id, 'pending')}
                >
                  Pendiente
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
