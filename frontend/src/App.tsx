import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { AccountPage } from './pages/AccountPage'
import { LogoutButton } from './components/LogoutButton'
import { TripsPage } from './pages/TripsPage'
import { TripDetailPage } from './pages/TripDetailPage'
import tripTogetherLogo from './assets/triptogether-logo.png'
import './App.css'

function Shell() {
  const { state } = useAuth()
  return (
    <div className="app-shell">
      <header className="site-header">
        <Link className="brand" to="/">
          <span className="brand-logo" aria-hidden="true" style={{ backgroundImage: `url(${tripTogetherLogo})` }} />
          <span>TripTogether</span>
        </Link>
        <nav className="header-nav" aria-label="Main navigation">
          {state.status === 'authenticated' ? <>
            <Link to="/trips">Trips</Link>
            <Link to="/account">Account</Link>
            <span className="user-chip"><span>{state.user.username}</span><span>{state.user.email}</span></span>
            <LogoutButton className="nav-button" />
          </> : state.status === 'anonymous' ? <>
            <Link to="/login">Log in</Link>
            <Link to="/register">Create account</Link>
          </> : <span className="nav-status">{state.status === 'loading' ? 'Checking session...' : 'Session unavailable'}</span>}
        </nav>
      </header>

      <main className="page-content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/trips" element={<TripsPage />} />
            <Route path="/trips/:tripId" element={<TripDetailPage />} />
            <Route path="/account" element={<AccountPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>

      <footer className="site-footer">
        <span>TripTogether</span>
        <span>Plan together. Travel together.</span>
      </footer>
    </div>
  )
}

function HomePage() {
  const { state } = useAuth()
  const authenticated = state.status === 'authenticated'
  return <>
    <section className="landing" aria-labelledby="page-title">
      <div className="landing-copy-block">
        <p className="eyebrow">Make every plan feel shared</p>
        <h1 id="page-title">Plan together.<br /><em>Travel better.</em></h1>
        <p className="landing-copy">Build the journey, keep every detail in sync, and split shared costs without a spreadsheet.</p>
        <div className="actions landing-actions">
        {authenticated ? <Link className="primary-button" to="/trips">Go to trips</Link> : <>
          <Link className="primary-button" to="/register">Start planning</Link>
          <Link className="retry-button" to="/login">Log in</Link>
        </>}
        </div>
      </div>
      <div className="landing-preview" aria-label="TripTogether product preview">
        <div className="preview-top"><span className="preview-kicker">UPCOMING TRIP</span><span className="preview-dot" /></div>
        <h2>Tokyo Adventure</h2><p>May 12 – May 18 · 4 travelers</p>
        <div className="preview-days"><strong>Day 1</strong><span>09:00 · Tsukiji Market</span><span>13:00 · Asakusa</span><span>18:30 · Shibuya</span></div>
        <div className="preview-finance"><span>Trip spending <strong>$1,248</strong></span><span>You are owed <strong>+$86</strong></span></div>
      </div>
    </section>
    <section className="landing-values" aria-label="TripTogether features">
      <div><span className="value-number">01</span><strong>Plan together</strong><p>One shared place for every destination, date, and decision.</p></div>
      <div><span className="value-number">02</span><strong>Build the journey</strong><p>Organize each day with a clear itinerary your group can update.</p></div>
      <div><span className="value-number">03</span><strong>Split without the spreadsheet</strong><p>Track costs and understand what to settle at a glance.</p></div>
    </section>
  </>
}

function NotFoundPage() {
  return (
    <section className="not-found">
      <p className="eyebrow">404</p>
      <h1>Page not found</h1>
      <p>The page you requested does not exist.</p>
      <Link className="text-link" to="/">
        Return home
      </Link>
    </section>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider><Shell /></AuthProvider>
    </BrowserRouter>
  )
}

export default App
