import { boardLoaded, box, cards, expect, test } from './fixtures'

test('e2e_saved_view_opens_the_same_cards', async ({ api: served, page }) => {
  const query = 'type=bug&type=feature&label=ui&future=kept'
  await page.goto(`${served.url}/tickets?${query}`)
  await boardLoaded(page)
  const identities = () =>
    cards(page).evaluateAll((elements) =>
      elements.map(
        (element) =>
          `${element.getAttribute('data-repository') ?? ''}/${element.getAttribute('data-ticket') ?? ''}`,
      ),
    )
  const original = await identities()
  expect(original.length).toBeGreaterThan(0)
  const filter = page.getByRole('list', { name: 'Saved views', exact: true })
  const trigger = page.getByRole('button', { name: 'Views', exact: true })
  await trigger.click()
  await page.getByLabel('View name', { exact: true }).fill('My saved bugs')
  await page.getByRole('button', { name: 'Save view', exact: true }).click()
  await expect(filter.getByRole('link', { name: 'My saved bugs', exact: true })).toBeVisible()
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  await trigger.click()
  await filter.getByRole('link', { name: 'My saved bugs', exact: true }).click()
  await expect(page).toHaveURL(`${served.url}/tickets?${query}`)
  await expect.poll(identities).toStrictEqual(original)
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Search commands' }).fill('My saved bugs')
  await page.getByRole('option').filter({ hasText: 'My saved bugs' }).click()
  await expect(page).toHaveURL(`${served.url}/tickets?${query}`)
  await expect.poll(identities).toStrictEqual(original)
  await trigger.click()
  await filter.getByRole('button', { name: 'Delete view My saved bugs', exact: true }).click()
  await expect(filter.getByRole('link', { name: 'My saved bugs', exact: true })).toHaveCount(0)
  await page.reload()
  await boardLoaded(page)
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Search commands' }).fill('My saved bugs')
  await expect(page.getByRole('option').filter({ hasText: 'My saved bugs' })).toHaveCount(0)
})

test('e2e_the_save_view_form_stacks_its_button_under_a_wide_field', async ({
  api: served,
  page,
}) => {
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  await page.getByRole('button', { name: 'Views', exact: true }).click()
  const input = await box(page.getByLabel('View name', { exact: true }))
  const button = await box(page.getByRole('button', { name: 'Save view', exact: true }))
  expect(input.width).toBeGreaterThanOrEqual(150)
  expect(button.y).toBeGreaterThanOrEqual(input.y + input.height)
})
