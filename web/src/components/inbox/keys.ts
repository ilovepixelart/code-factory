// The Inbox from the keyboard. An item marks itself with `data-inbox-item` (its name) and
// `data-href` (its ticket's page); a question's choice controls carry `data-choice` (a number picks
// that choice, as a click does) and its Answer button `data-answer` (`a` answers with what is
// picked, the recommended choice until another is); a permission request carries
// `data-permission`. The keys act only outside a
// field and a dialog, as every page shortcut does.

import type { Router } from 'vue-router'
import { dialogOpen, typing } from '../../lib/keys'

const ITEM = '[data-inbox-item]'

/** The item the focus is in, if any. */
function current(): HTMLElement | null {
  const active = document.activeElement
  return active instanceof HTMLElement ? active.closest<HTMLElement>(ITEM) : null
}

/** Move the focus to the next (`by` 1) or previous (-1) item, the first or last from outside. */
function step(region: HTMLElement, by: 1 | -1): boolean {
  const items = [...region.querySelectorAll<HTMLElement>(ITEM)]
  if (!items.length) return false
  const at = items.indexOf(current() ?? items[0] ?? region)
  const here = current() === null ? (by === 1 ? -1 : items.length) : at
  const next = items[Math.min(items.length - 1, Math.max(0, here + by))]
  next?.focus()
  next?.scrollIntoView({ block: 'nearest' })
  return next !== undefined
}

/** Press the button `selector` names inside the focused item. */
function press(selector: string): boolean {
  const button = current()?.querySelector<HTMLButtonElement>(selector)
  if (!button || button.disabled) return false
  button.click()
  return true
}

/** What a key does in the Inbox, true when it acted (the key is then the Inbox's alone). */
function act(key: string, region: HTMLElement, router: Router): boolean {
  if (key === 'j') return step(region, 1)
  if (key === 'k') return step(region, -1)
  if (/^[1-9]$/.test(key)) return press(`[data-choice="${key}"]`)
  if (key === 'a') return press('[data-answer]')
  // AI Elements' Confirmation draws Deny then Allow in its actions.
  if (key === 'y' && current()?.hasAttribute('data-permission'))
    return press('[data-slot="item-actions"] > button:last-of-type')
  if (key === 'n' && current()?.hasAttribute('data-permission'))
    return press('[data-slot="item-actions"] > button:first-of-type')
  const item = current()
  if (key === 'Enter' && item && document.activeElement === item && item.dataset.href) {
    void router.push(item.dataset.href)
    return true
  }
  return false
}

/** The handler for the page: it runs before the app's own keys, so `n` denies a focused
 *  permission instead of opening a new ticket, and leaves every key it does not use to them. */
export function inboxKeys(region: () => HTMLElement | null, router: Router) {
  return (event: KeyboardEvent): void => {
    if (event.metaKey || event.ctrlKey || event.altKey) return
    if (typing(event.target) || dialogOpen()) return
    const area = region()
    if (area && act(event.key, area, router)) {
      event.preventDefault()
      event.stopImmediatePropagation()
    }
  }
}
