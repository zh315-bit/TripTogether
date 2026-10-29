import { BrowserRouter, Link, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { AccountPage } from './pages/AccountPage'
import { ForgotPasswordPage, ResetPasswordPage } from './pages/PasswordResetPages'
import { DemoPage, TryDemoButton } from './pages/DemoPage'
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
        <p className="eyebrow">Shared trip planning</p>
        <h1 id="page-title">Plan together.<br /><em>Travel lighter.</em></h1>
        <p className="landing-copy">Pin the places everyone wants to see on one shared map, shape each day into a route, and split costs without a spreadsheet.</p>
        <div className="actions landing-actions">
          <TryDemoButton />
          <Link className="retry-button" to="/register">Start planning</Link>
          <Link className="text-link landing-login" to="/login">Log in</Link>
        </div>
        <p className="landing-demo-hint muted-copy">The demo opens a shared Kyoto trip as Mika; open a second window as Jonas to watch changes arrive live.</p>
      </div>
      <figure className="landing-preview" aria-label="TripTogether product preview: a shared trip map with a three-stop day route">
        <div className="preview-top"><span className="preview-kicker">Tokyo · 4 travelers</span><span className="preview-stamp">Day 1</span></div>
        <svg className="preview-map" viewBox="0 0 320 170" role="img" aria-label="Map sketch with a dashed route between three member-coloured pins">
          <path className="preview-sea" d="M0 120 C60 100 110 150 170 128 S270 92 320 112 V170 H0Z" />
          <path className="preview-river" d="M40 0 C70 50 30 90 80 170" />
          <path className="preview-route" d="M64 58 C110 30 150 44 178 76 S246 120 262 64" />
          <g className="preview-pin" transform="translate(64 58)"><circle r="11" fill="#1c6fc2" /><text y="4">A</text></g>
          <g className="preview-pin" transform="translate(178 76)"><circle r="11" fill="#d71f1f" /><text y="4">B</text></g>
          <g className="preview-pin" transform="translate(262 64)"><circle r="11" fill="#127f36" /><text y="4">C</text></g>
        </svg>
        <div className="preview-days"><span><strong>1</strong> Tsukiji Market</span><span><strong>2</strong> Senso-ji</span><span><strong>3</strong> Shibuya at dusk</span></div>
        <figcaption className="preview-finance"><span>Straight-line route <strong>11.6 km</strong></span><span>You are owed <strong>+$86</strong></span></figcaption>
      </figure>
    </section>
    <section className="landing-values" aria-label="TripTogether features">
      <div><span className="value-number">01</span><strong>One shared map</strong><p>Everyone pins their ideas, colour-coded by who suggested them.</p></div>
      <div><span className="value-number">02</span><strong>Days that flow</strong><p>Turn places into a daily route and get a shorter order suggested.</p></div>
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
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/demo" element={<DemoPage />} />
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
