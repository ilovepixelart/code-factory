import { defineConfig } from '@playwright/test'
import { OWNER_TOKEN } from './e2e/owner'

// The Vue board's browser tests on the server (web/e2e): each test serves a fresh sample on
// its own port, so they run side by side. Scrollbars drawn, as the owner sees them: headless
// Chromium hides them unless `--hide-scrollbars` is left out.
export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  reporter: [['list']],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    // A stalled action fails on its own with its locator named, not at the test limit (CF-482:
    // about 3 times the slowest step measured). A call passing its own `timeout` keeps it.
    actionTimeout: 10_000,
    viewport: { width: 1600, height: 900 },
    // The owner's sign-in cookie for every board these tests start (e2e/owner.ts):
    // a cookie is not bound to a port, so one covers them all; the board sets it on the one
    // loopback name it prints, so both are held (CF-1438).
    storageState: {
      cookies: ['127.0.0.1', 'localhost'].map((domain) => ({
        name: 'code_factory_owner',
        value: OWNER_TOKEN,
        domain,
        path: '/',
        expires: -1,
        httpOnly: true,
        secure: false,
        sameSite: 'Strict' as const,
      })),
      origins: [],
    },
    launchOptions: { ignoreDefaultArgs: ['--hide-scrollbars'] },
  },
})
