// CF-1217: the pull request's state label on a card, one colour per state, readable in both
// themes, served by the server over the api sample.

import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, card, contrast, expect, hold, serve, test, variant, useTheme } from './fixtures'

// The record each state reads from, and the Badge variant its tone draws (docs/design.md, Theme:
// an error destructive, a warning default, info, success and merged secondary, quiet outline).
const STATES: [string, Record<string, unknown>, string][] = [
  ['open', { state: 'open', ci: 'passed' }, 'secondary'],
  ['approved', { state: 'open', ci: 'passed', review: 'approved' }, 'secondary'],
  ['draft', { state: 'open', ci: 'passed', draft: true }, 'outline'],
  ['conflict', { state: 'open', ci: 'passed', conflict: true }, 'default'],
  ['checks failing', { state: 'open', ci: 'failed' }, 'destructive'],
  ['checks running', { state: 'open', ci: 'pending' }, 'default'],
  ['closed', { state: 'closed', ci: 'passed' }, 'outline'],
  ['merged', { state: 'merged', ci: 'passed' }, 'secondary'],
]

test('e2e_a_pull_label_per_state_meets_the_contrast_minimum', async ({ browser }) => {
  const { served, stop } = await serve('api', 'false', false)
  const file = join(served.home, 'pull_requests.json')
  const pulls = JSON.parse(readFileSync(file, 'utf8')) as Record<string, Record<string, unknown>>
  // CF-3 has no pull request and no checks record of the board's own.
  const key = (Object.keys(pulls).find((k) => k.endsWith('/CF-2')) ?? '').replace(/CF-2$/, 'CF-3')
  const page = await (await browser.newContext()).newPage()
  try {
    for (const [words, record, tone] of STATES) {
      pulls[key] = {
        head: 'abc',
        url: 'https://github.com/o/r/pull/3',
        at: '1790000000.0',
        review: '',
        draft: false,
        conflict: false,
        ...record,
      }
      writeFileSync(file, JSON.stringify(pulls))
      await page.goto(`${served.url}/tickets`)
      const label = card(page, 'CF-3').getByText(words, { exact: true })
      await label.waitFor({ timeout: TIMEOUT })
      await expect(label).toHaveAttribute('data-slot', 'badge')
      expect(await variant(label), words).toBe(tone)
      await hold(page)
      for (const theme of ['light', 'dark']) {
        await useTheme(page, theme)
        expect(await contrast(label), `${words} ${theme}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  } finally {
    stop()
  }
})
