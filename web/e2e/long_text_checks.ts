// What the long text spec (CF-1292) measures: the elements wider than their box, the page's
// sideways scroll and the footer of a ticket, at each size and theme.

import type { Locator, Page } from '@playwright/test'
import { OPEN_OVERLAY, TIMEOUT, card, scroller, settle, useTheme, type Served } from './fixtures'
import { SIZES, THEMES } from './long_text_fixture'

/**
 * What in `scope` is wider than its box and not cut with an ellipsis and its full text in `title`
 * (on the element or one holding it); a sideways scroller is one too, but for a table's container
 * on a phone.
 */
function offenders(scope: Locator, narrow: boolean): Promise<string[]> {
  return scope.evaluate((root, allowTable) => {
    const named = (e: HTMLElement): string =>
      `${e.tagName.toLowerCase()}.${e.classList[0] ?? ''} "${e.textContent.trim().slice(0, 24)}"`
    const scrolls = (s: CSSStyleDeclaration): boolean =>
      s.overflowX === 'auto' || s.overflowX === 'scroll'
    // Visually hidden text (`sr-only`) is one clipped pixel by design.
    const hidden = (e: HTMLElement, s: CSSStyleDeclaration): boolean =>
      e.getClientRects().length === 0 || (e.clientWidth <= 1 && s.overflowX === 'hidden')
    const cut = (e: HTMLElement, s: CSSStyleDeclaration): boolean => {
      const full = e instanceof HTMLInputElement ? e.value : e.textContent.trim()
      const title = e.closest('[title]')?.getAttribute('title') ?? ''
      return s.textOverflow === 'ellipsis' && title !== '' && title.includes(full)
    }
    const problem = (e: HTMLElement): string => {
      const s = getComputedStyle(e)
      if (hidden(e, s) || e.scrollWidth <= e.clientWidth + 1) return ''
      if (scrolls(s)) {
        return allowTable && e.dataset.slot === 'table-container'
          ? ''
          : `scrolls sideways: ${named(e)}`
      }
      return cut(e, s)
        ? ''
        : `overflows: ${named(e)} ${String(e.scrollWidth)} > ${String(e.clientWidth)}`
    }
    return [root, ...root.querySelectorAll('*')]
      .filter((e): e is HTMLElement => e instanceof HTMLElement)
      .map(problem)
      .filter((text) => text !== '')
  }, narrow)
}

function sideways(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

/** Each size and theme of the surface `scope` names, once `show` has drawn it: what is wrong. */
export async function problems(
  page: Page,
  show: () => Promise<void>,
  scope: () => Locator,
  after?: () => Promise<string[]>,
): Promise<string[]> {
  const found: string[] = []
  for (const size of SIZES) {
    await page.setViewportSize(size)
    await show()
    for (const theme of THEMES) {
      await useTheme(page, theme)
      const label = `${String(size.width)} px, ${theme}`
      const wide = await sideways(page)
      found.push(
        ...(await offenders(scope(), size.width < 800)).map((text) => `${label}: ${text}`),
        ...(wide > 0 ? [`${label}: the page scrolls ${String(wide)} px sideways`] : []),
        ...((await after?.())?.map((text) => `${label}: ${text}`) ?? []),
      )
    }
  }
  return found
}

export type View = 'panel' | 'page'

/** CF-90's form, as the board's side panel or as its page, drawn and at rest. */
export async function showTicket(page: Page, served: Served, view: View): Promise<void> {
  const target = view === 'page' ? '/tickets/sample/CF-90' : '/tickets'
  await page.goto(`${served.url}${target}`)
  if (view === 'panel') await card(page, 'CF-90').getByRole('paragraph').getByRole('link').click()
  const form = page.getByRole('form', { name: 'Edit ticket CF-90' })
  await form.getByRole('region', { name: 'Status' }).waitFor({ timeout: TIMEOUT })
  await settle(page, OPEN_OVERLAY)
}

/** The frame a ticket scrolls in. */
export function frame(page: Page, view: View): Locator {
  return view === 'page' ? scroller(page) : page.getByRole('dialog')
}

/** Scroll the ticket to its end; whether its last property value is above its footer. */
export async function sourceAboveFooter(page: Page, view: View): Promise<string[]> {
  await frame(page, view).evaluate((e) => {
    const area = e.querySelector('.overflow-y-auto') ?? e
    area.scrollTop = area.scrollHeight
  })
  const [value, footer] = await Promise.all([
    page.getByTestId('source').boundingBox(),
    page.getByTestId('ticket-footer').boundingBox(),
  ])
  return value && footer && value.y + value.height > footer.y + 1
    ? ['the Source value is under the footer']
    : []
}

/**
 * The values of the properties rail that take more than two lines of their own text size: a read
 * only or link value stacked beside its label (CF-1293). An input is one line by construction.
 */
export function stackedProperties(page: Page, view: View): Promise<string[]> {
  return frame(page, view)
    .getByRole('complementary', { name: 'Properties' })
    .evaluate((rail) =>
      [...rail.querySelectorAll<HTMLElement>('[data-slot="field"] > :not(:first-child)')]
        .filter((e) => e.getClientRects().length > 0)
        .map((e) => {
          const line = Number.parseFloat(getComputedStyle(e).lineHeight)
          const lines = Math.round(e.getBoundingClientRect().height / line)
          return lines > 2
            ? `${e.textContent.trim().slice(0, 24)} takes ${String(lines)} lines`
            : ''
        })
        .filter((text) => text !== ''),
    )
}
