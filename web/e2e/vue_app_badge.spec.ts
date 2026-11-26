// CF-1276: every status tone's Badge is readable in both themes (the /design page draws them all).

import { TIMEOUT, contrast, expect, hold, test, useTheme } from './fixtures'

const WORDS = ['quiet', 'info', 'success', 'warning', 'error', 'primary']

test('e2e_every_badge_tone_meets_the_contrast_minimum', async ({ api: served, page }) => {
  await page.goto(`${served.url}/design`)
  const region = page.getByRole('region', { name: 'Badges and states' })
  await expect(region.getByText('primary', { exact: true })).toHaveCount(1, { timeout: TIMEOUT })
  await hold(page)
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    for (const word of WORDS) {
      const measured = await contrast(region.getByText(word, { exact: true }))
      expect.soft(measured, `${theme} ${word}`).toBeGreaterThanOrEqual(4.5)
    }
  }
})
