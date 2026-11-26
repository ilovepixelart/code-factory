// CF-1210: every overlay (drawer, dialog, command menu) is one shell: Escape and a click on the
// backdrop close it, Tab stays inside it, and a phone gets a drawer full screen and a dialog
// inside its width.

import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, card, expect, test } from './fixtures'

interface Overlay {
  name: string
  open: (page: Page) => Promise<Locator>
}

const OVERLAYS: Overlay[] = [
  {
    name: 'command menu',
    open: async (page) => {
      await page.keyboard.press('Meta+k')
      return page.getByRole('dialog', { name: 'Command menu' })
    },
  },
  {
    name: 'new ticket drawer',
    open: async (page) => {
      await page.keyboard.press('n')
      return page.getByRole('dialog', { name: 'New ticket', exact: true })
    },
  },
  {
    name: 'ticket drawer',
    open: async (page) => {
      await card(page, 'CF-2').click()
      await page.getByRole('button', { name: 'Delete' }).waitFor({ timeout: TIMEOUT })
      return page.getByRole('dialog', { name: /CF-2$/ })
    },
  },
  {
    name: 'shortcut dialog',
    open: async (page) => {
      await page.keyboard.press('?')
      return page.getByRole('dialog', { name: 'Keyboard shortcuts' })
    },
  },
  {
    name: 'confirm dialog',
    open: async (page) => {
      await card(page, 'CF-2').click()
      await page.getByRole('button', { name: 'Delete' }).click()
      return page.getByRole('alertdialog', { name: 'Delete ticket', exact: true })
    },
  },
]

const CLOSERS: Record<string, (page: Page) => Promise<void>> = {
  escape: (page) => page.keyboard.press('Escape'),
  the_backdrop: (page) => page.mouse.click(2, 450),
}

for (const [how, close] of Object.entries(CLOSERS)) {
  for (const overlay of OVERLAYS) {
    test(`e2e_overlay_${overlay.name.replaceAll(' ', '_')}_closes_on_${how}`, async ({
      writesBoard: page,
    }) => {
      const shell = await overlay.open(page)
      await expect(shell).toBeVisible()
      await close(page)
      await expect(shell).toBeHidden()
    })
  }
}

for (const overlay of OVERLAYS) {
  test(`e2e_overlay_${overlay.name.replaceAll(' ', '_')}_keeps_the_focus_inside`, async ({
    writesBoard: page,
  }) => {
    const shell = await overlay.open(page)
    await expect(shell).toBeVisible()
    for (let tab = 0; tab < 12; tab++) {
      await page.keyboard.press('Tab')
      expect(await shell.evaluate((d) => d.contains(document.activeElement))).toBe(true)
    }
  })
}

// A confirmation answers with its own Cancel, so it has no Close of its own (shadcn-vue's
// AlertDialog).
test('e2e_every_drawer_and_dialog_has_a_title_and_one_close', async ({ writesBoard: page }) => {
  for (const overlay of OVERLAYS.filter(
    (o) => !['command menu', 'confirm dialog'].includes(o.name),
  )) {
    const shell = await overlay.open(page)
    await expect(
      shell.getByRole('button', { name: 'Close', exact: true }),
      overlay.name,
    ).toHaveCount(1)
    await expect(shell.getByRole('heading'), overlay.name).not.toHaveCount(0)
    await page.keyboard.press('Escape')
    await expect(shell).toBeHidden()
  }
})

/** Where the box of an overlay rests: it slides or scales in first. */
async function resting(shell: Locator): Promise<{ left: number; right: number; width: number }> {
  const read = () =>
    shell.evaluate((d) => {
      const box = d.getBoundingClientRect()
      return { left: box.left, right: box.right, width: box.width }
    })
  await expect.poll(async () => (await read()).right).toBeLessThanOrEqual(390)
  return read()
}

test('e2e_a_drawer_and_a_dialog_fit_a_phone', async ({ writesBoard: page }) => {
  await page.setViewportSize({ width: 390, height: 800 })
  for (const overlay of OVERLAYS.filter((o) => o.name !== 'command menu')) {
    const shell = await overlay.open(page)
    const box = await resting(shell)
    expect(box.left).toBeGreaterThanOrEqual(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await page.keyboard.press('Escape')
    await expect(shell).toBeHidden()
  }
})

test('e2e_a_drawer_fills_a_phone', async ({ writesBoard: page }) => {
  await page.setViewportSize({ width: 390, height: 800 })
  await page.keyboard.press('n')
  const box = await resting(page.getByRole('dialog', { name: 'New ticket', exact: true }))
  expect([box.left, box.width]).toStrictEqual([0, 390])
})
