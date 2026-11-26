// A ticket's own keys (the Ticket group of lib/shortcuts.ts): each presses the control of the open
// ticket that carries its `data-shortcut` name, the same button the person would click, so a key
// can do nothing that control cannot. On the ticket page and in its panel alike.

import { useEventListener } from '@vueuse/core'
import type { Ref } from 'vue'
import { gPending, typing } from './keys'
import { TICKET_KEYS } from './shortcuts'

const OPEN_DIALOG = ':is([role=dialog], [role=alertdialog])[data-state=open]'

function held(event: KeyboardEvent): boolean {
  return event.metaKey || event.ctrlKey || event.altKey
}

/** Press the ticket control the key names, inside `root`; nothing when the key is not the
 *  ticket's, is typed in a field, comes after `g`, or another dialog than the ticket's is open. */
export function onTicketKey(event: KeyboardEvent, root: Element | null): void {
  const target = TICKET_KEYS[event.key]
  if (!target || !root?.isConnected || event.defaultPrevented) return
  if (held(event) || typing(event.target) || gPending()) return
  const dialog = document.querySelector(OPEN_DIALOG)
  if (dialog && !dialog.contains(root)) return
  const control = root.querySelector<HTMLElement>(`[data-shortcut="${target}"]`)
  if (!control || control.hasAttribute('disabled') || control.ariaDisabled === 'true') return
  event.preventDefault()
  if (control instanceof HTMLTextAreaElement || control instanceof HTMLInputElement) control.focus()
  else control.click()
}

/** The ticket keys for the form `root`, listening while the form lives. */
export function useTicketKeys(root: Ref<Element | null>): void {
  useEventListener(document, 'keydown', (event) => {
    onTicketKey(event, root.value)
  })
}
