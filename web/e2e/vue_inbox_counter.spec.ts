// CF-296: the Inbox count in the sidebar, open and folded, over the writes sample (two waiting).

import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, box, expect, test } from './fixtures'

function inbox(page: Page): Locator {
  return page.getByRole('navigation', { name: 'Pages' }).getByRole('link', { name: /^Inbox/ })
}

/** The Inbox entry of the sidebar: its link, and the count and dot drawn beside it. */
function entry(page: Page): Locator {
  return page
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('listitem')
    .filter({ has: inbox(page) })
}

type Box = Awaited<ReturnType<typeof box>>

/** Whether two drawn boxes do not overlap. */
function apart(a: Box, b: Box): boolean {
  return (
    a.x >= b.x + b.width || a.x + a.width <= b.x || a.y >= b.y + b.height || a.y + a.height <= b.y
  )
}

test('e2e_the_open_sidebar_counts_in_the_design_language', async ({ served, writesBoard }) => {
  const chip = entry(writesBoard).getByText('1', { exact: true })
  await chip.waitFor({ timeout: TIMEOUT })
  const look = await chip.evaluate((el) => {
    const style = getComputedStyle(el)
    return { text: (el as HTMLElement).innerText, numbers: style.fontVariantNumeric }
  })
  const quiet = await writesBoard.context().newPage()
  await quiet.route('**/api/inbox/count', (route) =>
    route.fulfill({ json: { count: 0, latest: '' } }),
  )
  const counted = quiet.waitForResponse('**/api/inbox/count')
  await quiet.goto(`${served.url}/tickets`)
  await counted

  expect(look).toStrictEqual({ text: '1', numbers: 'tabular-nums' })
  await expect(entry(quiet)).toHaveText('Inbox')
})

test('e2e_the_folded_sidebar_keeps_the_inbox_icon_whole', async ({ served, writesBoard }) => {
  await writesBoard.evaluate(() => {
    localStorage.setItem('codeFactorySidebar', 'folded')
  })
  await writesBoard.goto(`${served.url}/tickets`)
  const link = inbox(writesBoard)
  const dot = entry(writesBoard).getByTestId('inbox-dot')
  await dot.waitFor({ timeout: TIMEOUT })
  const icon = await box(link.getByRole('img', { includeHidden: true }))
  const mark = await box(dot)
  const colours = await dot.evaluate((el) => ({
    dot: getComputedStyle(el).backgroundColor,
    text: getComputedStyle(document.body).color,
  }))

  expect(apart(mark, icon)).toBe(true)
  expect(mark.width).toBe(8)
  expect(colours.dot).toBe(colours.text)
  await expect(link).toHaveAccessibleName('Inbox, 1 waiting')
})
