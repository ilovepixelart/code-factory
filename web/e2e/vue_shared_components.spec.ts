// CF-1282: the shared components as one set, walked on the /design page that draws each in every
// variant and state, and on the Inbox, whose disabled Answer buttons and small grey hints were
// reported too faint. Every text, a disabled control's included, meets 4.5:1 in both themes; every
// control is reached by Tab and shows a ring, has an accessible name, and the /design page does not
// scroll sideways at 390 px.

import type { Page } from '@playwright/test'
import { TIMEOUT, contrast, expect, hold, serve, settle, test, useTheme } from './fixtures'

const MINIMUM = 4.5
const CONTROLS = 'main :is(a[href], button, input, select, textarea, summary):not([tabindex="-1"])'

async function openDesign(page: Page, url: string): Promise<void> {
  await page.goto(`${url}/design`)
  await expect(page.getByRole('heading', { name: 'Fields' })).toBeVisible({ timeout: TIMEOUT })
  await hold(page)
}

/**
 * Mark each drawn element of the main area that holds words of its own, or a typed value; how
 * many, and how many of them are disabled.
 */
function markText(page: Page): Promise<{ marked: number; disabled: number }> {
  return page.evaluate(() => {
    document.querySelectorAll('[data-text]').forEach((e) => {
      e.removeAttribute('data-text')
    })
    let marked = 0
    let disabled = 0
    for (const element of document.querySelectorAll('main *')) {
      const typed =
        element instanceof HTMLInputElement
          ? !['checkbox', 'radio', 'hidden'].includes(element.type) && element.value !== ''
          : element instanceof HTMLTextAreaElement && element.value !== ''
      const own = [...element.childNodes].some(
        (node) => node.nodeType === Node.TEXT_NODE && (node.textContent ?? '').trim() !== '',
      )
      const box = element.getBoundingClientRect()
      if (!(own || typed) || box.width === 0 || box.height === 0) continue
      element.setAttribute('data-text', String(marked))
      marked += 1
      if (element.closest(':disabled, [aria-disabled="true"]')) disabled += 1
    }
    return { marked, disabled }
  })
}

/** The words, or the value, of each marked element that reads under the minimum in this theme. */
async function faint(page: Page, theme: string, at: number): Promise<string[]> {
  const sample = page.locator(`[data-text="${String(at)}"]`)
  const measured = await contrast(sample)
  if (measured >= MINIMUM) return []
  const words = ((await sample.textContent()) ?? (await sample.inputValue())).trim().slice(0, 40)
  return [`${theme} ${measured.toFixed(2)} "${words}"`]
}

async function faintTexts(
  page: Page,
): Promise<{ read: string[]; marked: number; disabled: number }> {
  const read: string[] = []
  let counted = { marked: 0, disabled: 0 }
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    counted = await markText(page)
    for (let at = 0; at < counted.marked; at += 1) read.push(...(await faint(page, theme, at)))
  }
  return { read, ...counted }
}

test('e2e_every_text_of_the_shared_components_meets_the_contrast_minimum_in_both_themes', async ({
  api: served,
  page,
}) => {
  await openDesign(page, served.url)
  const { read, marked, disabled } = await faintTexts(page)

  expect(marked).toBeGreaterThan(100)
  expect(disabled).toBeGreaterThan(8)
  expect(read).toStrictEqual([])
})

test('e2e_the_inbox_text_meets_the_contrast_minimum_in_both_themes', async ({ page }) => {
  // The metrics sample has an item in every section of the Inbox, questions included.
  const { served, stop } = await serve('metrics', 'false', false)
  try {
    await page.goto(`${served.url}/inbox`)
    await page.getByRole('region', { name: 'Ready for review' }).waitFor({ timeout: TIMEOUT })
    await hold(page)
    const { read, marked, disabled } = await faintTexts(page)

    expect(marked).toBeGreaterThan(30)
    expect(disabled).toBeGreaterThan(0)
    expect(read).toStrictEqual([])
  } finally {
    stop()
  }
})

/** What Tab reaches from the top of the page, one stop at a time, and which stops show no ring. */
async function walkTab(
  page: Page,
): Promise<{ enabled: number; reached: string[]; bare: string[] }> {
  const enabled = await page.evaluate(
    (selector) =>
      [...document.querySelectorAll<HTMLButtonElement>(selector)].filter(
        (n) => !n.disabled && n.getBoundingClientRect().width > 0,
      ).length,
    CONTROLS,
  )
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
  })
  const reached = new Set<string>()
  const bare: string[] = []
  for (let step = 0; step < enabled + 30; step += 1) {
    await page.keyboard.press('Tab')
    // A ring may ease in (a Button's transition): read it where it rests.
    await settle(page)
    const seen = await page.evaluate((controls) => {
      const el = document.activeElement
      if (!el || el === document.body) return null
      // A ring is an outline of some width, or a shadow with an offset, blur or spread: a button's
      // own shadow is all zeros.
      const ringed = (node: Element): boolean => {
        const style = getComputedStyle(node)
        const outline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0
        const lengths = style.boxShadow.match(/-?\d+(?:\.\d+)?px/g) ?? []
        return outline || lengths.some((length) => parseFloat(length) !== 0)
      }
      // A control drawn inside a box of its own (an input group, a tags or number field) shows
      // the ring on that box: an ancestor that holds no other control.
      const boxed = (): boolean => {
        for (let at = el.parentElement; at && at !== document.body; at = at.parentElement) {
          if (at.querySelectorAll(controls).length > 1) return false
          if (ringed(at)) return true
        }
        return false
      }
      const name = el.getAttribute('aria-label') ?? el.textContent.trim().slice(0, 30)
      return {
        ring: ringed(el) || boxed(),
        label: `${el.tagName.toLowerCase()} ${name}`,
      }
    }, CONTROLS)
    if (seen) reached.add(seen.label)
    if (seen && !seen.ring) bare.push(seen.label)
  }
  return { enabled, reached: [...reached], bare }
}

test('e2e_every_control_is_reached_by_tab_and_shows_a_focus_ring', async ({
  api: served,
  page,
}) => {
  await openDesign(page, served.url)
  const { enabled, reached, bare } = await walkTab(page)

  expect(enabled).toBeGreaterThan(30)
  expect(reached.length).toBeGreaterThan(30)
  expect(bare).toStrictEqual([])
})

test('e2e_the_ticket_title_field_shows_a_ring_when_reached_by_tab', async ({
  api: served,
  page,
}) => {
  await page.goto(`${served.url}/tickets/sample/CF-1`)
  const field = page
    .getByRole('form', { name: 'Edit ticket CF-1' })
    .getByRole('textbox', { name: 'Title' })
  await field.waitFor({ timeout: TIMEOUT })
  await field.focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await settle(page)

  await expect(field).toBeFocused()
  // A ring is an outline of some width, or a shadow with an offset, blur or spread.
  const ring = await field.evaluate((el) => {
    const style = getComputedStyle(el)
    const outline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0
    const lengths = style.boxShadow.match(/-?\d+(?:\.\d+)?px/g) ?? []
    return outline || lengths.some((length) => parseFloat(length) !== 0)
  })
  expect(ring).toBe(true)
})

test('e2e_every_control_has_an_accessible_name', async ({ api: served, page }) => {
  await openDesign(page, served.url)
  const tree = await page.getByRole('main').ariaSnapshot()
  const nameless = tree
    .split('\n')
    .map((line) => line.trim())
    .filter((line) =>
      /^- (button|link|textbox|combobox|checkbox|radio|switch|tab|searchbox|spinbutton)( \[[^\]]*\])*:?$/.test(
        line,
      ),
    )

  expect(nameless).toStrictEqual([])
  expect(tree).toContain('button "Icon button"')
})

/** How far the page's scroller scrolls sideways, and the controls that reach past the screen
 *  outside a scroller. */
function overflow(page: Page): Promise<{ sideways: number; beyond: string[] }> {
  return page.evaluate(() => {
    const main = document.querySelector('[data-scroller]')
    const sideways = main ? main.scrollWidth - main.clientWidth : -1
    const beyond = [
      ...document.querySelectorAll('main :is(a[href], button, input, select, textarea)'),
    ]
      .filter(
        (e) =>
          e.getBoundingClientRect().right > window.innerWidth + 1 &&
          !e.parentElement?.closest('main .overflow-x-auto, main .overflow-auto'),
      )
      .map((e) => e.textContent.trim().slice(0, 30) || e.tagName)
    return { sideways, beyond }
  })
}

test('e2e_the_design_page_does_not_scroll_sideways_at_390_px', async ({ api: served, page }) => {
  await page.setViewportSize({ width: 390, height: 800 })
  await openDesign(page, served.url)
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)

    expect(await overflow(page), theme).toStrictEqual({ sideways: 0, beyond: [] })
  }
})
