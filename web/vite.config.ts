import path from 'node:path'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// The server's default port, or the one `CODE_FACTORY_PORT` names for a server started beside Vite.
const SERVER = `http://127.0.0.1:${process.env.CODE_FACTORY_PORT ?? '4000'}`

export default defineConfig({
  // Tailwind minifies the CSS; Vite's own CSS minifier is off (build.cssMinify below).
  plugins: [vue(), tailwindcss({ optimize: { minify: true } })],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // `vite` serves the app, the server the API and the sign-in link. The server answers only a
    // loopback `Host` on its own port and only a change whose `Origin` is its own, so both are
    // rewritten to the target; the cookie it sets is the browser's for the page's own host.
    proxy: Object.fromEntries(
      ['/api', '/owner'].map((path) => [
        path,
        { target: SERVER, changeOrigin: true, headers: { Origin: SERVER } },
      ]),
    ),
  },
  build: {
    // Package data of the Python package, so a wheel carries the app (platform/web/webapp.py).
    outDir: '../src/code_factory/platform/web/dist',
    emptyOutDir: true,
    // No data: URIs, so the Content-Security-Policy needs none.
    assetsInlineLimit: 0,
    // Tailwind minifies the stylesheet already (plugins above).
    cssMinify: false,
  },
  // Two kinds of Vitest test, each its own project: `unit` runs in Node with no DOM (`pnpm test`,
  // the gate and CI), `component` renders Vue components into happy-dom (`pnpm test:component`,
  // on demand). The browser tests in tests/e2e run under Playwright (playwright.config.ts).
  test: {
    projects: [
      {
        extends: true,
        test: { name: 'unit', include: ['tests/unit/**/*.test.ts'], environment: 'node' },
      },
      {
        extends: true,
        test: {
          name: 'component',
          include: ['tests/component/**/*.test.ts'],
          environment: 'happy-dom',
        },
      },
    ],
    setupFiles: ['tests/support/unstubbed-fetch.ts'],
    // Unovis's ES modules import directories, which Node refuses: Vite resolves them instead.
    server: { deps: { inline: ['@unovis/vue', '@unovis/ts'] } },
    // A test that asserts nothing passes whatever the code does (CF-547).
    expect: { requireAssertions: true },
    // Floors of the unit project, measured on 2026-11-26 when the component tests left the gate:
    // raised as coverage rises, never lowered.
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/generated/**'],
      reporter: ['text-summary', 'lcovonly'],
      thresholds: { lines: 70, branches: 72, functions: 62, statements: 69 },
    },
  },
})
