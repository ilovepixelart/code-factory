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
  // The browser tests run under Playwright (playwright.config.ts), not Vitest.
  test: {
    include: ['src/**/*.test.ts'],
    setupFiles: ['src/test/unstubbed-fetch.ts'],
    // Unovis's ES modules import directories, which Node refuses: Vite resolves them instead.
    server: { deps: { inline: ['@unovis/vue', '@unovis/ts'] } },
    // A test that asserts nothing passes whatever the code does (CF-547).
    expect: { requireAssertions: true },
    // Floors from the 2026-10-07 measurement (CF-364): raised as coverage rises, never lowered.
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/**/*.test.ts', 'src/generated/**', 'src/test/**'],
      reporter: ['text-summary', 'lcovonly'],
      thresholds: { lines: 84, branches: 74, functions: 71, statements: 82 },
    },
  },
})
