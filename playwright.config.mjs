/**
 * Playwright E2E test configuration.
 * Tests run against a live app instance (Docker or dev server).
 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120000,
  retries: 1,
  workers: 1, // Sequential — tests share state (registered user, project)
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8001',
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
    // Self-signed certificate on a test stack: E2E_INSECURE_TLS=1
    ignoreHTTPSErrors: !!process.env.E2E_INSECURE_TLS,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  reporter: [['html', { open: 'never' }], ['list']],
})
