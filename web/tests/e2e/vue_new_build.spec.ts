// CF-1298: a tab left open across a board restart learns of the new build from the board's next
// answer, offers a reload, and loads its next navigation afresh; it never reloads by itself.

import { boardLoaded, expect, test } from './fixtures'

const OTHER_BUILD = 'ffffffff'

test('a tab on an older build shows the notice with Reload and loads the next page afresh', async ({
  page,
  served,
}) => {
  let restarted = false
  await page.route('**/api/board', async (route) => {
    const response = await route.fetch()
    const headers = restarted
      ? { ...response.headers(), 'x-code-factory-build': OTHER_BUILD }
      : response.headers()
    await route.fulfill({ response, headers })
  })
  let documents = 0
  page.on('request', (request) => {
    if (request.resourceType() === 'document') documents++
  })
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  await expect(page.getByRole('button', { name: 'Reload' })).toHaveCount(0)

  const before = documents

  restarted = true
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))

  await expect(page.getByText('The board was updated; reload the page to see it.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reload' })).toBeVisible()
  expect(documents).toBe(before)

  await page.getByRole('link', { name: 'Inbox' }).click()

  await expect(page).toHaveURL(/\/inbox$/)
  await expect.poll(() => documents).toBe(before + 1)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
