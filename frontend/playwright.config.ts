import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests drive the real stack: a FastAPI backend on 8011 (migrated
 * to head, fake geocoder) and the Vite dev server on 5175 pointed at it. Both
 * are started here, so `npm run e2e` is the whole command locally and in CI.
 * The backend needs DATABASE_URL and JWT_SECRET_KEY from the environment or
 * the repository's .env, exactly like a normal development run.
 */
const CI = Boolean(process.env.CI)
const API = 'http://127.0.0.1:8011'
const APP = 'http://127.0.0.1:5175'
const python = process.env.E2E_PYTHON ?? 'python'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  workers: CI ? 2 : undefined,
  retries: CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: APP,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${python} -m alembic upgrade head && ${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8011`,
      cwd: '../backend',
      url: `${API}/ready`,
      reuseExistingServer: !CI,
      timeout: 120_000,
      env: {
        APP_ENV: 'development',
        GEOCODER_PROVIDER: 'fake',
        // localhost is a second origin for the demo recording's side-by-side windows.
        CORS_ORIGINS: JSON.stringify([APP, APP.replace('127.0.0.1', 'localhost')]),
        // The suite registers and signs in far faster than a person; the
        // brute-force limits have their own backend tests.
        RATE_LIMIT_LOGIN: 'off',
        RATE_LIMIT_REGISTER: 'off',
        DEMO_MODE: '1',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5175 --strictPort',
      url: APP,
      reuseExistingServer: !CI,
      timeout: 120_000,
      env: { VITE_API_BASE_URL: API },
    },
  ],
})
