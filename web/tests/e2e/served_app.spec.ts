// CF-203 acceptance flow: the server serves the Vue app it carries and its API.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { extname } from 'node:path'
import { ROOT, TIMEOUT, expect, serve, sidebar, test } from './fixtures'
import { OWNER_COOKIE } from './owner'

// One server for the file, over a sample of its own.
test.describe.configure({ mode: 'serial' })

let appUrl: string
let stop: () => void

test.beforeAll(async () => {
  const started = await serve('empty')
  appUrl = started.served.url
  stop = started.stop
})

test.afterAll(() => {
  stop()
})

/** The version `pyproject.toml` declares. */
function projectVersion(): string {
  const text = readFileSync(join(ROOT, 'pyproject.toml'), 'utf8')
  const found = /^version\s*=\s*"([^"]+)"/m.exec(text)?.[1]
  if (!found) throw new Error('pyproject.toml declares no version')
  return found
}

/** The status, content type and body of a GET, as the signed-in owner (CF-624). */
async function fetchText(url: string): Promise<[number, string, string]> {
  const response = await fetch(url, {
    headers: { Cookie: OWNER_COOKIE },
    signal: AbortSignal.timeout(5000),
  })
  return [response.status, response.headers.get('content-type') ?? '', await response.text()]
}

test('e2e_every_answer_names_the_build', async () => {
  const response = await fetch(`${appUrl}/`, { headers: { Cookie: OWNER_COOKIE } })

  expect(response.headers.get('x-code-factory-build')).toMatch(/^[0-9a-f]{64}$/)
})

test('e2e_the_server_serves_its_page_and_its_files', async () => {
  const [status, kind, page] = await fetchText(`${appUrl}/`)
  const [, routedKind, routed] = await fetchText(`${appUrl}/tickets/x`)
  const assets = [...page.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1] ?? '')

  expect([status, kind.split(';')[0]]).toStrictEqual([200, 'text/html'])
  expect(page).toContain('<div id="app">')
  expect([routedKind.split(';')[0], routed]).toStrictEqual(['text/html', page])
  const suffixes = new Set(assets.map((a) => extname(a)))
  expect(suffixes.has('.js') && suffixes.has('.css')).toBe(true)
  const statuses = await Promise.all(assets.map(async (a) => (await fetchText(`${appUrl}${a}`))[0]))
  expect(statuses).toStrictEqual(assets.map(() => 200))
})

test('e2e_the_page_shows_the_server_version', async ({ browser }) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(`${appUrl}/`)
  await page.getByRole('navigation', { name: 'Pages' }).waitFor({ timeout: TIMEOUT })
  const version = projectVersion()

  await expect(sidebar(page).getByRole('button', { name: 'Choose a repository' })).toContainText(
    'Code Factory',
  )
  const about: unknown = JSON.parse((await fetchText(`${appUrl}/api/about`))[2])

  expect(about).toStrictEqual({ name: 'code-factory', version })
  await context.close()
})

for (const theme of ['light', 'dark'] as const) {
  test(`e2e_the_page_uses_the_board_theme[${theme}]`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: theme })
    const page = await context.newPage()
    await page.goto(`${appUrl}/`)
    await page.getByRole('navigation', { name: 'Pages' }).waitFor({ timeout: TIMEOUT })
    const colours = await page.evaluate(() => {
      const s = getComputedStyle(document.body)
      const probe = document.createElement('span')
      probe.style.backgroundColor = 'var(--background)'
      probe.style.color = 'var(--foreground)'
      document.body.append(probe)
      const expected = getComputedStyle(probe)
      const tokens = [expected.backgroundColor, expected.color]
      probe.remove()
      return {
        scheme: s.colorScheme,
        actual: [s.backgroundColor, s.color],
        tokens,
      }
    })

    expect(colours.scheme).toBe(theme)
    expect(colours.actual).toStrictEqual(colours.tokens)
    await context.close()
  })
}

test('e2e_the_api_docs_page_loads_under_the_policy', async ({ browser }) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.addInitScript(() => {
    const seen: string[] = []
    ;(window as unknown as { violations: string[] }).violations = seen
    document.addEventListener('securitypolicyviolation', (e) =>
      seen.push(`${e.violatedDirective} ${e.blockedURI}`),
    )
  })
  await page.goto(`${appUrl}/api/docs/`)
  await expect(
    page.getByText('/api/about', { exact: true }).filter({ visible: true }),
  ).not.toHaveCount(0)

  expect(
    await page.evaluate(() => (window as unknown as { violations: string[] }).violations),
  ).toStrictEqual([])
  await context.close()
})
