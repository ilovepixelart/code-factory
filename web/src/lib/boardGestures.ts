// The tickets page's document listeners: choosing and opening cards, its keyboard
// shortcuts and panning the board, removed with the page.

import { useEventListener } from '@vueuse/core'
import { dialogOpen, typing } from './keys'
import * as selection from './selection'

export interface BoardActions {
  openPanel: (repository: string, ticket: string) => void
  focusSearch: () => void
}

export interface BoardGestures {
  /** Bound to the pannable area's pointerdown. */
  panStart: (event: PointerEvent) => void
}

// Cmd, Ctrl or Shift and a click chooses a card for a bulk action instead of following it
// (select.js); a click on its menu does not. Capture phase: it must run before the card's link.
function onChoose(event: MouseEvent): void {
  if (!(event.metaKey || event.ctrlKey || event.shiftKey)) return
  const target = event.target instanceof Element ? event.target : null
  const card = target?.closest<HTMLElement>('li[data-ticket]')
  if (!card || target?.closest('[data-js-menu]')) return
  event.preventDefault()
  event.stopPropagation()
  selection.toggle(selection.keyOf(card.dataset.repository ?? '', card.dataset.ticket ?? ''))
}

// Pressing on empty board space and dragging sideways pans the board (pan.js).
const INTERACTIVE = 'li[data-ticket], button, a, input, select, textarea, summary, label'

/** A key pressed without Cmd or Ctrl (nor Alt, unless `alt` allows it), outside a field and a dialog. */
function plain(event: KeyboardEvent, alt: boolean): boolean {
  const held = event.metaKey || event.ctrlKey || (!alt && event.altKey)
  return !held && !typing(event.target) && !dialogOpen()
}

export function useBoardGestures(actions: BoardActions): BoardGestures {
  // A plain click on a card, or on its title, opens its panel; the title
  // stays a link for the keyboard, a middle click and the browser's link menu.
  function onOpen(event: MouseEvent): void {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
    const target = event.target instanceof Element ? event.target : null
    const body = target?.closest('[data-js-card-body]')
    const card = body?.closest<HTMLElement>('li[data-ticket]')
    if (!body || !card) return
    const link = target?.closest('a[href]')
    if (link && !link.matches('[data-js-card-link]')) return
    event.preventDefault()
    actions.openPanel(card.dataset.repository ?? '', card.dataset.ticket ?? '')
  }
  function onKey(event: KeyboardEvent): void {
    if (event.key === 'Escape' && selection.chosen.size && !dialogOpen()) selection.clearSelection()
    if (event.key === '/' && plain(event, true)) {
      event.preventDefault()
      actions.focusSearch()
    }
  }

  let pan: { board: HTMLElement; x: number; left: number } | null = null
  function panStart(event: PointerEvent): void {
    const area = (event.target as Element).closest<HTMLElement>('[data-js-pan]')
    if (!area || event.button !== 0 || (event.target as Element).closest(INTERACTIVE)) return
    pan = { board: area, x: event.clientX, left: area.scrollLeft }
    area.classList.add('cursor-grabbing')
  }
  function panMove(event: PointerEvent): void {
    if (pan) pan.board.scrollLeft = pan.left - (event.clientX - pan.x)
  }
  function panEnd(): void {
    pan?.board.classList.remove('cursor-grabbing')
    pan = null
  }

  useEventListener(document, 'click', onChoose, true)
  useEventListener(document, 'click', onOpen, true)
  useEventListener(document, 'keydown', onKey)
  useEventListener(document, 'pointermove', panMove)
  useEventListener(document, 'pointerup', panEnd)
  return { panStart }
}
