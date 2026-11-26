// CF-435: the Inbox's layout measured in the browser, over the metrics sample (an item in every
// section), served unfollowed so the sample stays as written.

import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import {
  TIMEOUT,
  box,
  contrast,
  expect,
  hold,
  scroller,
  seedInbox,
  serve,
  test,
  useTheme,
  type Served,
} from './fixtures'

/** 280 characters with no space, wider than any row at 1600 px. */
const LONG_PATH = 'src/very/deeply/nested/module/path/'.repeat(8)

/** Serve the metrics sample, changed by `prepare`, with `/inbox` open and every section drawn. */
async function openInbox(page: Page, prepare: (served: Served) => void = () => undefined) {
  const { served, stop } = await serve('metrics', 'false', false)
  prepare(served)
  await page.goto(`${served.url}/inbox`)
  await page.getByRole('region', { name: 'Ready for review' }).waitFor({ timeout: TIMEOUT })
  return stop
}

/** The vertical centre of the text an element holds, as drawn. */
function textCentre(text: Locator): Promise<number> {
  return text.evaluate((e) => {
    const range = document.createRange()
    range.selectNodeContents(e)
    const drawn = range.getBoundingClientRect()
    return drawn.top + drawn.height / 2
  })
}

test('e2e_a_long_stop_reason_wraps_inside_its_row', async ({ page }) => {
  const stop = await openInbox(page, (served) => {
    const path = join(served.home, 'runs.json')
    const runs = JSON.parse(readFileSync(path, 'utf8')) as { halted: string }[]
    for (const run of runs) if (run.halted) run.halted = `the agent stopped because ${LONG_PATH}`
    writeFileSync(path, JSON.stringify(runs))
  })
  try {
    const reason = page
      .getByRole('region', { name: 'Stopped agents' })
      .getByText(`Stopped: the agent stopped because ${LONG_PATH}`)
    await expect(reason).toBeVisible()
    const measure = (e: Element) => ({ scroll: e.scrollWidth, client: e.clientWidth })

    const main = await scroller(page).evaluate(measure)
    const paragraph = await reason.evaluate(measure)

    expect(main.scroll).toBe(main.client)
    expect(paragraph.scroll).toBeLessThanOrEqual(paragraph.client)
  } finally {
    stop()
  }
})

test('e2e_every_inbox_row_has_the_same_space_above_and_below', async ({ page }) => {
  const stop = await openInbox(page)
  try {
    const rows = await page
      .getByRole('main')
      .getByRole('listitem')
      .evaluateAll((all) =>
        all.map((row) => {
          const edge = row.getBoundingClientRect()
          const parts = [...row.children]
            .map((c) => c.getBoundingClientRect())
            .filter((c) => c.height > 0)
          const above = Math.min(...parts.map((p) => p.top)) - edge.top
          const below = edge.bottom - Math.max(...parts.map((p) => p.bottom))
          const section = row.closest('section')?.getAttribute('aria-labelledby') ?? ''
          return { section, above: Math.round(above), below: Math.round(below) }
        }),
      )

    // One row fewer since CF-1228: a review whose checks failed is listed once, not twice.
    expect(rows.length).toBeGreaterThanOrEqual(8)
    expect(rows.filter((r) => Math.abs(r.above - r.below) > 1)).toStrictEqual([])
  } finally {
    stop()
  }
})

test('e2e_a_failing_check_s_age_lines_up_with_its_button', async ({ page }) => {
  const stop = await openInbox(page)
  try {
    const row = page.getByRole('region', { name: 'Failing checks' }).getByRole('listitem')
    const button = await box(row.getByRole('link', { name: 'Open pull request' }))

    const age = await textCentre(row.getByText(/^\d+(\.\d)?[mhd]$/))

    expect(Math.abs(age - (button.y + button.height / 2))).toBeLessThanOrEqual(2)
  } finally {
    stop()
  }
})

test('e2e_the_recommended_badge_shows_in_both_themes', async ({ page, served }) => {
  seedInbox(served, {
    ticket: 'CF-1',
    question: {
      text: 'Which storage should the importer use?',
      choices: [
        { text: 'SQLite', recommended: true, description: 'Already a dependency' },
        { text: 'Postgres' },
      ],
    },
  })
  await page.goto(`${served.url}/inbox`)
  const badge = page
    .getByRole('group', { name: 'Choices for Which storage should the importer use?' })
    .getByText('Recommended', { exact: true })
  await expect(badge).toBeVisible()
  const measured: Record<string, number> = {}
  // CF-1020-R3: the theme's colours held where they start easing until `useTheme` finishes them.
  await hold(page)

  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    measured[theme] = await contrast(badge, true)
  }

  expect(measured.light).toBeGreaterThanOrEqual(1.15)
  expect(measured.dark).toBeGreaterThanOrEqual(1.15)
})
