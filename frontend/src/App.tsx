import { BrowserRouter, Link, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { AccountPage } from './pages/AccountPage'
import { LogoutButton } from './components/LogoutButton'
import { WorkspacePage } from './workspace/WorkspacePage'
import tripTogetherLogo from './assets/triptogether-logo.png'
import './App.css'

/** Public and account pages: header, footer and the breathing travel backdrop. */
function PublicLayout() {
  const { state } = useAuth()
  return (
    <div className="app-shell breathing-bg">
      <header className="site-header">
        <Link className="brand" to="/">
          <span className="brand-logo" aria-hidden="true" style={{ backgroundImage: `url(${tripTogetherLogo})` }} />
          <span>TripTogether</span>
        </Link>
        <nav className="header-nav" aria-label="Main navigation">
          {state.status === 'authenticated' ? <>
            <Link to="/trips">Open map</Link>
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
        <Outlet />
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
  // Signed-in travellers land on their map, not the marketing page.
  if (state.status === 'authenticated') return <Navigate to="/trips" replace />
  return <>
    <section className="landing" aria-labelledby="page-title">
      <div className="landing-copy-block">
        <p className="eyebrow">Make every plan feel shared</p>
        <h1 id="page-title">Plan together.<br /><em>Travel better.</em></h1>
        <p className="landing-copy">Build the journey, keep every detail in sync, and split shared costs without a spreadsheet.</p>
        <div className="actions landing-actions">
          <Link className="primary-button" to="/register">Start planning</Link>
          <Link className="retry-button" to="/login">Log in</Link>
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
      <AuthProvider>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/account" element={<AccountPage />} />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Route>
          {/* The workspace fills the viewport: its own top bar, no site header or footer. */}
          <Route element={<ProtectedRoute />}>
            <Route path="/trips" element={<WorkspacePage />} />
            <Route path="/trips/:tripId" element={<WorkspacePage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
