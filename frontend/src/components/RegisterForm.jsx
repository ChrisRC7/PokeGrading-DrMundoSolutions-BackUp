import { useState } from 'react'
import { registerUser } from '../api'

export default function RegisterForm() {
  const [form, setForm] = useState({
    email: '', password: '', alias: '', accept_disclosure: false,
    country: 'CR', preferred_language: 'es',
  })
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm((f) => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    setLoading(true)
    try {
      const data = await registerUser(form)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Registrar cuenta</h2>
      <form onSubmit={handleSubmit}>
        <label>Email
          <input name="email" type="email" value={form.email} onChange={handleChange} required />
        </label>
        <label>Contraseña (mín. 8 caracteres)
          <input name="password" type="password" value={form.password} onChange={handleChange} required minLength={8} />
        </label>
        <label>Alias
          <input name="alias" type="text" value={form.alias} onChange={handleChange} required />
        </label>
        <label>País
          <select name="country" value={form.country} onChange={handleChange}>
            <option value="CR">Costa Rica</option>
            <option value="PA">Panamá</option>
            <option value="MX">México</option>
            <option value="CO">Colombia</option>
            <option value="CL">Chile</option>
            <option value="AR">Argentina</option>
          </select>
        </label>
        <label>Idioma preferido
          <select name="preferred_language" value={form.preferred_language} onChange={handleChange}>
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>
        </label>
        <label className="checkbox-label">
          <input name="accept_disclosure" type="checkbox" checked={form.accept_disclosure} onChange={handleChange} />
          Acepto los términos de divulgación
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Registrando…' : 'Registrar'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}
      {result && (
        <div className="alert success">
          <p><strong>¡Cuenta creada!</strong></p>
          <p>Usuario: {result.alias} ({result.role})</p>
          <p>Email: {result.email}</p>
          <p>País: {result.country} · Idioma: {result.preferred_language}</p>
        </div>
      )}
    </div>
  )
}
