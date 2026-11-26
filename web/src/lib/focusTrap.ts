const FOCUSABLE =
  ':is(a[href], button, input, select, textarea, summary, [tabindex]):not([disabled], [tabindex="-1"])'

/** Keeps Tab inside `root`: Tab on its last control goes to the first, Shift+Tab on the first to
 *  the last, and Tab from outside it goes in. */
export function trapTab(event: KeyboardEvent, root: HTMLElement | null): void {
  const items = [...(root?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])].filter(
    (item) => item.getClientRects().length > 0,
  )
  const edge = event.shiftKey ? items[0] : items.at(-1)
  const target = event.shiftKey ? items.at(-1) : items[0]
  if (!target || (document.activeElement !== edge && root?.contains(document.activeElement))) return
  event.preventDefault()
  target.focus()
}
