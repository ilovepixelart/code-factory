// Keyboard shortcuts act only while no one is typing and no dialog is open.

export function typing(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest('input, textarea, select, [contenteditable]') !== null
  )
}

/** When `g` was last pressed: the key after it, within a second, names a page, so no other
 *  shortcut may take that key meanwhile. */
export const sequence = { gAt: 0 }
const G_WINDOW = 1000

export function gPending(now = Date.now()): boolean {
  return now - sequence.gAt < G_WINDOW
}

/** A Dialog, Sheet or AlertDialog is open: their content carries the role and `data-state`. */
export function dialogOpen(): boolean {
  return document.querySelector(':is([role=dialog], [role=alertdialog])[data-state=open]') !== null
}
