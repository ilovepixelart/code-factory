// The page does not jump while it loads: each page's title and controls are teleported into the
// shell's header, so the shell holds its first paint until they are in place.

import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

const LIMIT = 0.02
const PAGES: [string, string][] = [
  ['/tickets', 'Tickets'],
  ['/memory', 'Memory'],
  ['/flow', 'Flow'],
  ['/archive', 'Archive'],
]

async function watchShifts(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const shifts: number[] = []
    Object.assign(window, { __shifts: shifts })
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const { value, hadRecentInput } = entry as PerformanceEntry & {
          value: number
          hadRecentInput: boolean
        }
        if (!hadRecentInput) shifts.push(value)
      }
    }).observe({ type: 'layout-shift', buffered: true })
  })
}

async function shifted(page: Page): Promise<number> {
  const shifts = await page.evaluate(() => (window as unknown as { __shifts: number[] }).__shifts)
  return shifts.reduce((sum: number, value: number) => sum + value, 0)
}

/** Time for a late shift to be reported; a shift has no event to wait on. */
function lateShifts(page: Page): Promise<unknown> {
  return page.evaluate(() => new Promise((done) => setTimeout(done, 2000)))
}

for (const [name, size] of [
  ['a_phone', { width: 390, height: 844 }],
  ['a_desktop', { width: 1600, height: 900 }],
] as const) {
  for (const [path, title] of PAGES) {
    test(`e2e_on_${name}_${title.toLowerCase()}_loads_without_the_page_jumping`, async ({
      api,
      page,
    }) => {
      await page.setViewportSize(size)
      await watchShifts(page)
      await page.goto(`${api.url}${path}`)
      await expect(page.getByRole('heading', { name: title, level: 1 })).toBeVisible()
      await lateShifts(page)

      expect(await shifted(page)).toBeLessThan(LIMIT)
    })
  }
}

test('e2e_on_a_phone_moving_between_pages_does_not_jump', async ({ api, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await watchShifts(page)
  await page.goto(`${api.url}/tickets`)
  await expect(page.getByRole('heading', { name: 'Tickets', level: 1 })).toBeVisible()
  await lateShifts(page)
  const before = await shifted(page)
  // On a phone the page links are in the sidebar's sheet.
  await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  await page
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('link', { name: 'Memory' })
    .click()
  await expect(page.getByRole('heading', { name: 'Memory', level: 1 })).toBeVisible()
  await lateShifts(page)

  expect((await shifted(page)) - before).toBeLessThan(LIMIT)
})
