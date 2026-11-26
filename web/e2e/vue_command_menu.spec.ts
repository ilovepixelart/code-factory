// CF-848: the command menu, served by the server over the writes sample state.

import { OWNER_COOKIE } from './owner'
import { TIMEOUT, boardLoaded, card, expect, test } from './fixtures'

// CF-848-R5
test('e2e_a_long_title_stays_inside_the_command_menu', async ({ served, page }) => {
  const title = `A bug in flight ${'with a title far longer than the menu is wide '.repeat(3)}`
  const renamed = await fetch(`${served.url}/api/tickets/sample/CF-2`, {
    method: 'PATCH',
    headers: { Cookie: OWNER_COOKIE, 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  expect(renamed.status).toBe(200)
  await page.goto(`${served.url}/tickets`)
  await card(page, 'CF-2').waitFor({ timeout: TIMEOUT })

  await page.keyboard.press('Meta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  await menu.getByRole('combobox', { name: 'Search commands' }).fill('bug flight')
  const row = menu.getByRole('option').filter({ hasText: 'A bug in flight' })
  await expect(row).toHaveCount(1)

  const list = menu.getByRole('listbox', { name: 'Commands' })
  const [listBox, hintBox] = await Promise.all([
    list.boundingBox(),
    row.getByText('sample', { exact: true }).boundingBox(),
  ])
  const label = row.getByText(/^CF-2 A bug in flight/)
  expect(await list.evaluate((e) => e.scrollWidth - e.clientWidth)).toBe(0)
  expect(
    await label.evaluate(
      (e) => e.scrollWidth > e.clientWidth && getComputedStyle(e).textOverflow === 'ellipsis',
    ),
  ).toBe(true)
  expect(hintBox && listBox && hintBox.x + hintBox.width <= listBox.x + listBox.width).toBe(true)
})

test('e2e_arrowing_down_the_command_menu_keeps_the_active_option_in_view', async ({
  api,
  page,
}) => {
  await page.goto(`${api.url}/tickets`)
  await boardLoaded(page)
  await page.keyboard.press('ControlOrMeta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  const list = menu.getByRole('listbox')
  const search = menu.getByRole('combobox', { name: 'Search commands' })
  await expect(list.getByRole('option', { name: /Stop every agent/ })).toBeAttached()

  for (let i = 0; i < 16; i += 1) await page.keyboard.press('ArrowDown')

  // The active option is the one the search field names as its active descendant.
  const active = (): Promise<{ y: number; height: number } | null> =>
    search.evaluate((field) => {
      const id = field.getAttribute('aria-activedescendant')
      const option = id ? document.getElementById(id) : null
      if (option?.getAttribute('role') !== 'option') return null
      const { y, height } = option.getBoundingClientRect()
      return { y, height }
    })
  await expect.poll(active).not.toBeNull()
  await expect
    .poll(async () => {
      const [outer, inner] = await Promise.all([list.boundingBox(), active()])
      return Boolean(
        outer && inner && inner.y >= outer.y && inner.y + inner.height <= outer.y + outer.height,
      )
    })
    .toBe(true)
})
