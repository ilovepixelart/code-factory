// A page chunk the board no longer serves, as after the binary is replaced under an open tab: the
// page loads afresh once (CF-318), and when that does not bring it the notice says so (CF-542).

import { expect, test, toasts, boardLoaded } from './fixtures'

test('a page whose chunk is gone shows after one reload', async ({ page, served }) => {
  // The old tab asks for a name the new binary does not serve, every time, until a fresh load
  // brings the new names: the chunk is refused until the page's document is fetched a second time.
  let documents = 0
  let loaded = 0
  page.on('request', (request) => {
    if (request.resourceType() === 'document') documents++
  })
  page.on('response', (response) => {
    if (response.request().resourceType() === 'document') loaded++
  })
  await page.route(/\/assets\/AgentsPage-[^/]+\.js$/, async (route) => {
    if (documents < 2) {
      await route.fulfill({ status: 404, body: '' })
      return
    }
    await route.continue()
  })
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)

  await page.getByRole('link', { name: 'Agents', exact: true }).click()

  await expect(page.getByRole('heading', { name: /^Agents/, level: 2 })).toBeVisible()
  // The board, then the Agents page loaded afresh once: Chromium may cancel and restart the
  // request for an address the page is already on, which loads it once.
  expect(loaded).toBe(2)
})

test('a page still missing after its reload says the board was updated', async ({
  page,
  served,
}) => {
  await page.route(/\/assets\/AgentsPage-[^/]+\.js$/, (route) =>
    route.fulfill({ status: 404, body: '' }),
  )
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)

  await page.getByRole('link', { name: 'Agents', exact: true }).click()

  await expect(toasts(page)).toContainText('The board was updated; reload the page to see it.')
})
