// Server-rendered markdown put into the page. The HTML
// comes only from that renderer, which escapes raw HTML and refuses unsafe links; it is parsed
// with DOMParser, whose documents run no scripts, and the page's policy refuses inline scripts.

import type { Directive } from 'vue'

/** Each heading `top - 1` levels lower, so the text's h1 becomes an h`top` (at most h6). */
function demote(body: HTMLElement, top: number): void {
  const shift = top - 1
  if (shift <= 0) return
  for (const heading of body.querySelectorAll('h1, h2, h3, h4, h5, h6')) {
    const level = Math.min(6, Number(heading.tagName.slice(1)) + shift)
    const lower = body.ownerDocument.createElement(`h${String(level)}`)
    for (const { name, value } of heading.attributes) lower.setAttribute(name, value)
    lower.replaceChildren(...heading.childNodes)
    heading.replaceWith(lower)
  }
}

/** Each table in typeset's `typeset-scroll` wrapper, so a wide one scrolls inside its own frame
 *  instead of pushing the page sideways on a narrow screen. */
function scrollTables(body: HTMLElement): void {
  for (const table of body.querySelectorAll('table')) {
    const frame = body.ownerDocument.createElement('div')
    frame.className = 'typeset-scroll'
    table.replaceWith(frame)
    frame.append(table)
  }
}

// The directive's argument, when given, is the level the text's own h1 takes, so its headings
// sit under the section that shows it.
function fill(element: HTMLElement, html: string, top?: string): void {
  const parsed = new DOMParser().parseFromString(html, 'text/html')
  if (top) demote(parsed.body, Number(top))
  scrollTables(parsed.body)
  element.replaceChildren(
    ...[...parsed.body.childNodes].map((node) => document.importNode(node, true)),
  )
}

export const vRendered: Directive<HTMLElement, string> = {
  mounted: (element, { value, arg }) => {
    fill(element, value, arg)
  },
  updated: (element, { value, oldValue, arg }) => {
    if (value !== oldValue) fill(element, value, arg)
  },
}
