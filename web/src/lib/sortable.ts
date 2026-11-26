// Dragging cards: SortableJS with the board's settings on
// every card list. The card stays where it was dropped until the server's board arrives; only then
// is Sortable's move undone, in the same task, so the page draws the server's answer from a
// consistent DOM.

import Sortable from 'sortablejs'
import { ref, type Directive } from 'vue'

interface CardData {
  dataset: { repository?: string; ticket?: string }
}

/** Cards as `repository/id`, in their order. */
export function droppedOrder(cards: Iterable<CardData>): string[] {
  return [...cards].map((card) => `${card.dataset.repository ?? ''}/${card.dataset.ticket ?? ''}`)
}

export interface Drop {
  repository: string
  id: string
  stage: string
  order: string[]
  /** Put the card back where it was picked up. */
  undo: () => void
}

export interface Sorting {
  /** A lane's lists share a group of their own; a lane takes only its own cards. */
  group: string
  start: () => void
  /** A drop, or null when the card was put back where it was. */
  drop: (drop: Drop | null) => void
}

/** Whether a card is being dragged: folded columns open to take the drop (columns.js). */
export const dragging = ref(false)

const sorting = new WeakMap<HTMLElement, Sorting>()
const instances = new WeakMap<HTMLElement, Sortable>()

export const vSortable: Directive<HTMLElement, Sorting> = {
  mounted(list, { value }) {
    sorting.set(list, value)
    const instance = Sortable.create(list, {
      group: value.group,
      animation: 150,
      // Pointer events instead of native drag and drop: the same in every browser and on touch
      // screens, and a drag the page can style.
      forceFallback: true,
      fallbackOnBody: true,
      ghostClass: 'sortable-ghost',
      fallbackClass: 'sortable-fallback',
      // CF-840: a card lifts only after a press held still for 250 ms, mouse and touch alike, so a
      // click opens the ticket without the card jumping.
      delay: 250,
      delayOnTouchOnly: false,
      touchStartThreshold: 5,
      // A press on a card's menu opens the menu, not a drag.
      filter: '[data-js-menu]',
      preventOnFilter: false,
      onStart: () => {
        dragging.value = true
        sorting.get(list)?.start()
      },
      onEnd: (event) => {
        dragging.value = false
        const handlers = sorting.get(list)
        const { item, from, to, oldIndex, newIndex } = event
        if (from === to && oldIndex === newIndex) {
          handlers?.drop(null)
          return
        }
        handlers?.drop({
          repository: item.dataset.repository ?? '',
          id: item.dataset.ticket ?? '',
          stage: to.dataset.stage ?? '',
          order: droppedOrder(to.querySelectorAll<HTMLElement>('li[data-ticket]')),
          undo: () => {
            item.remove()
            from.insertBefore(item, from.children[oldIndex ?? 0] ?? null)
          },
        })
      },
    })
    instances.set(list, instance)
  },
  updated(list, { value }) {
    sorting.set(list, value)
    instances.get(list)?.option('group', value.group)
  },
  beforeUnmount(list) {
    instances.get(list)?.destroy()
    instances.delete(list)
  },
}
