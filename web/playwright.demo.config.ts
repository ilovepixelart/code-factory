import { defineConfig } from '@playwright/test'
import shared from './playwright.config'

// The README's recordings (web/demo, CF-387): one worker, so the manifest gathers every flow, and
// a video of each page at a size a README shows.
export default defineConfig({
  ...shared,
  testDir: 'demo',
  fullyParallel: false,
  workers: 1,
  use: {
    ...shared.use,
    viewport: { width: 1280, height: 720 },
    video: { mode: 'on', size: { width: 1280, height: 720 } },
  },
})
