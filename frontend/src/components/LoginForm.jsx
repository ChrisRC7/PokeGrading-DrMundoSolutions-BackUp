import { useState } from 'react'
import { loginUser } from '../api'

export default function LoginForm({ onLogin }) {
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleChange = (e) =>
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await loginUser(form)
      onLogin(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Iniciar sesión</h2>
      <form onSubmit={handleSubmit}>
        <label>Email
          <input name="email" type="email" value={form.email} onChange={handleChange} required />
        </label>
        <label>Contraseña
          <input name="password" type="password" value={form.password} onChange={handleChange} required />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Ingresando…' : 'Iniciar sesión'}
        </button>
      </form>
      {error && <div className="alert error">{error}</div>}
    </div>
  )
}
