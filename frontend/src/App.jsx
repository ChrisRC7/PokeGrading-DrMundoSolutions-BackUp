import { useState } from 'react'
import RegisterForm from './components/RegisterForm'
import LoginForm from './components/LoginForm'
import AddCardForm from './components/AddCardForm'
import CardReviewList from './components/CardReviewList'
import SubmitCardForm from './components/SubmitCardForm'
import SubmissionsAdminList from './components/SubmissionsAdminList'

export default function App() {
  const [tab, setTab] = useState('register')
  const [adminTab, setAdminTab] = useState('review')
  const [user, setUser] = useState(null)

  const handleLogin = (data) => setUser(data)
  const handleLogout = () => setUser(null)

  // — Sesión activa —
  if (user) {
    return (
      <div className="app">
        <header>
          <h1>PokeGrading</h1>
          <div className="session-info">
            Bienvenido, <strong>{user.alias}</strong> ({user.role})
            <button className="link-btn" onClick={handleLogout}>Cerrar sesión</button>
          </div>
        </header>

        <main>
          {user.role === 'admin' ? (
            <>
              <nav className="tabs">
                <button
                  className={adminTab === 'review' ? 'active' : ''}
                  onClick={() => setAdminTab('review')}
                >
                  Revisar cartas
                </button>
                <button
                  className={adminTab === 'addCard' ? 'active' : ''}
                  onClick={() => setAdminTab('addCard')}
                >
                  Agregar carta
                </button>
                <button
                  className={adminTab === 'submissions' ? 'active' : ''}
                  onClick={() => setAdminTab('submissions')}
                >
                  Envíos
                </button>
              </nav>
              {adminTab === 'review' && <CardReviewList token={user.access_token} />}
              {adminTab === 'addCard' && <AddCardForm token={user.access_token} />}
              {adminTab === 'submissions' && <SubmissionsAdminList token={user.access_token} />}
            </>
          ) : (
            <SubmitCardForm token={user.access_token} />
          )}
        </main>
      </div>
    )
  }

  // — Sin sesión: registro / login —
  return (
    <div className="app">
      <header>
        <h1>PokeGrading</h1>
        <p>Sistema de gestión de cartas Pokémon</p>
      </header>

      <nav className="tabs">
        <button
          className={tab === 'register' ? 'active' : ''}
          onClick={() => setTab('register')}
        >
          Registrar cuenta
        </button>
        <button
          className={tab === 'login' ? 'active' : ''}
          onClick={() => setTab('login')}
        >
          Iniciar sesión
        </button>
      </nav>

      <main>
        {tab === 'register' && <RegisterForm />}
        {tab === 'login' && <LoginForm onLogin={handleLogin} />}
      </main>
    </div>
  )
}
