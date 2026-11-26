import { defineConfig } from '@playwright/test'
import { OWNER_TOKEN } from './tests/e2e/owner'

// The board's performance tests (web/perf, CF-552): on demand, never in the gate, one at a time so
// no test's load shows in another's times.
export default defineConfig({
  testDir: 'perf',
  testMatch: '*.perf.ts',
  globalSetup: './perf/global-setup.ts',
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  timeout: 600_000,
  use: {
    viewport: { width: 1600, height: 900 },
    storageState: {
      cookies: [
        {
          name: 'code_factory_owner',
          value: OWNER_TOKEN,
          domain: '127.0.0.1',
          path: '/',
          expires: -1,
          httpOnly: true,
          secure: false,
          sameSite: 'Strict',
        },
      ],
      origins: [],
    },
  },
})
