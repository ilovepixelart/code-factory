// CF-445: the Tickets page says the board is loading until the board's first answer, rather than
// showing a blank or empty board.

import { card, expect, serve, test } from './fixtures'

test('e2e_the_board_shows_loading_until_its_first_answer', async ({ page }) => {
  const { served, stop } = await serve('metrics', 'false', false)
  let answer: () => void = () => undefined
  const held = new Promise<void>((done) => {
    answer = done
  })
  await page.route('**/api/board', async (route) => {
    await held
    await route.continue()
  })

  try {
    await page.goto(`${served.url}/tickets`)
    const main = page.getByRole('main')

    await expect(main.getByText('Loading the board', { exact: true })).toBeVisible()
    await expect(main.getByRole('region')).toHaveCount(0)
    answer()
    const brd = main.getByRole('region', { name: 'Spec', exact: true })
    await expect(card(brd, 'CF-20')).toBeVisible()
    await expect(main.getByText('Loading the board', { exact: true })).toHaveCount(0)
  } finally {
    answer()
    stop()
  }
})
