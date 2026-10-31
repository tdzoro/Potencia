import { defineConfig, devices } from '@playwright/test'

/**
 * Browser suite for the authenticated journey.
 *
 * It runs against a real stack (API + built web app) and seeds its own account
 * through the API, so it never depends on fixtures already in a database.
 *
 *   API_BASE_URL=http://localhost:8010 \
 *   PLAYWRIGHT_BASE_URL=http://localhost:4173 \
 *   npm run e2e
 *
 * The system Chrome is used by default: downloading a second browser would add
 * ~150MB to a machine that already has one.
 */
/**
 * An empty CHROME_PATH means "use the browser Playwright installed", which is
 * what CI does. `??` would keep the empty string, so it is normalised here.
 */
const systemChrome = process.env.CHROME_PATH?.trim() || undefined

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          ...(systemChrome ? { executablePath: systemChrome } : {}),
          args: ['--no-sandbox'],
        },
      },
    },
  ],
})
