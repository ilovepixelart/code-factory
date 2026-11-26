// @vitest-environment happy-dom
// The ticket's headings form one outline under its page's h1 or its panel's h2 title: sections one
// level below it, a document's own headings below the Documents section, no level skipped and no
// second h1 (WCAG 1.3.1).

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const levels = (root: Element): { level: number; text: string }[] =>
  [...root.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((h) => ({
    level: Number(h.tagName.slice(1)),
    text: h.textContent.trim(),
  }))

/** The levels that skip one, after a title at `top`. */
function skips(headings: { level: number; text: string }[], top: number): string[] {
  let last = top
  return headings.flatMap((h) => {
    const skipped =
      h.level > last + 1 ? [`${h.text} h${String(h.level)} after h${String(last)}`] : []
    last = h.level
    return skipped
  })
}

test('the_page_sections_sit_under_its_h1_and_documents_under_their_section', async () => {
  const { page } = await form()
  const headings = levels(page.element)

  expect(headings.find((h) => h.text === 'Documents')?.level).toBe(2)
  expect(headings.find((h) => h.text === 'BRD')?.level).toBe(3)
  expect(headings.filter((h) => h.level === 1)).toEqual([])
  expect(skips(headings, 1)).toEqual([])
  page.unmount()
})

test('the_panel_sections_sit_under_its_h2_title', async () => {
  const { page } = await form(view, false, {}, false)
  const headings = levels(page.element)

  expect(headings.find((h) => h.text === 'BRD')?.level).toBe(4)
  expect(headings.filter((h) => h.level < 3)).toEqual([])
  expect(skips(headings, 2)).toEqual([])
  page.unmount()
})
