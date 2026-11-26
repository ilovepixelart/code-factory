// CF-1178: a browser without the owner's sign-in cookie is told why the board shows nothing and
// how to sign in, on every page of the shell; the header does not claim to be connecting.

import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  DESIGN_VIEWPORTS,
  captureDesign,
  dropSample,
  expect,
  prepareSample,
  start,
  test,
} from './fixtures'
import { OWNER_TOKEN } from './owner'

const READ_SENTENCE = "Reading the board needs the owner's sign-in."
const SETUP_TIMEOUT = 90_000

test.use({ storageState: { cookies: [], origins: [] } })

// CF-1178-R4, CF-1181-R7, CF-1181-A4
test('e2e_a_signed_out_browser_sees_how_to_sign_in', async ({ page, api }) => {
  for (const path of ['/inbox', '/flow']) {
    await page.goto(`${api.url}${path}`)
    const notice = page.getByRole('alert')

    await expect(notice.getByRole('heading')).toHaveText('This browser is not signed in')
    await expect(notice).toContainText(READ_SENTENCE)
    await expect(notice.getByRole('group', { name: 'Default browser' })).toHaveCount(1)
    await expect(notice.getByRole('group', { name: 'This browser' })).toHaveCount(1)
    await expect(notice.getByText('uv run code-factory open', { exact: true })).toHaveCount(1)
    await expect(notice.getByText('uv run code-factory sign-in', { exact: true })).toHaveCount(1)
    await expect(notice.getByRole('button', { name: 'Copy' })).toHaveCount(2)
    await expect(page.getByText('signed out', { exact: true })).toBeVisible()
    await expect(notice.getByRole('group', { name: 'This browser' })).toContainText(
      'within 60 seconds',
    )
  }
})

test('e2e_sign_in_fits_on_desktop_and_mobile', async ({ page, api }) => {
  for (const [mode, width, height, colorScheme] of DESIGN_VIEWPORTS) {
    await page.setViewportSize({ width, height })
    await page.emulateMedia({ colorScheme })
    await page.goto(`${api.url}/tickets`)
    await expect(page.getByRole('alert').getByRole('button', { name: 'Copy' })).toHaveCount(2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await captureDesign(page, `${mode}-sign-in`)
  }
})

test('e2e_first_run_fits_on_desktop_and_mobile', async ({ page }) => {
  test.setTimeout(SETUP_TIMEOUT)
  const state = mkdtempSync(join(tmpdir(), 'cf-first-run-'))
  const env = { CODE_FACTORY_STATE_DIR: state }
  const schema = prepareSample('empty', env)
  let stop: (() => void) | undefined
  try {
    const served = await start(schema, { env })
    stop = served.stop
    await page
      .context()
      .addCookies([{ name: 'code_factory_owner', value: OWNER_TOKEN, url: served.url }])
    for (const [mode, width, height, colorScheme] of DESIGN_VIEWPORTS) {
      await page.setViewportSize({ width, height })
      await page.emulateMedia({ colorScheme })
      await page.goto(`${served.url}/tickets`)
      const setup = page.getByRole('region', { name: /Get started/ })
      await expect(setup.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
      await expect(setup.getByLabel('Repository folder')).toBeVisible()
      await expect(setup.getByRole('button', { name: 'New ticket' })).toBeDisabled()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      )
      await captureDesign(page, `${mode}-first-run`)
    }
    await page.goto(`${served.url}/`)
    const sessions = page.getByRole('region', { name: /^Sessions/ })
    await expect(sessions.getByText(/^No (live sessions|sessions to show)$/)).toBeVisible()
    const appearance = await sessions.evaluate((section) => {
      const card = section.querySelector('[data-section-empty]')
      const empty = card?.querySelector('[data-slot="empty"]')
      const icon = card?.querySelector('[data-slot="empty-icon"]')
      if (!card || !empty || !icon) return null
      const center = (element: Element) => {
        const { left, width } = element.getBoundingClientRect()
        return left + width / 2
      }
      return {
        surface: card.getAttribute('data-slot'),
        textAlign: getComputedStyle(empty).textAlign,
        iconOffset: Math.round(center(card) - center(icon)),
      }
    })
    expect(appearance).toStrictEqual({ surface: 'card', textAlign: 'center', iconOffset: 0 })
    await captureDesign(page, 'dark-mobile-empty-sessions')
  } finally {
    stop?.()
    dropSample(schema)
    rmSync(state, { recursive: true, force: true })
  }
})
