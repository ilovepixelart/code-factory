// Dialogs, Sheets and menus render through Reka UI's Teleport; a test stubs it with its slot alone
// so they render in place and the wrapper finds them.
import { flushPromises, type DOMWrapper, type VueWrapper } from '@vue/test-utils'

export const INLINE = { Teleport: { template: '<slot />' } }

const OPEN = ':is([role="dialog"], [role="alertdialog"])[data-state="open"]'

/** Whether a Dialog, Sheet or AlertDialog is open in the wrapper. */
export function isOpen(wrapper: VueWrapper): boolean {
  return wrapper.find(OPEN).exists()
}

/** Escape, as the person presses it inside the open overlay. */
export async function escape(wrapper: VueWrapper): Promise<void> {
  wrapper
    .get(OPEN)
    .element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await flushPromises()
}

/** The button named `name` by its text or its aria-label. */
export function named(wrapper: VueWrapper, name: string): DOMWrapper<HTMLButtonElement> {
  const found = wrapper
    .findAll<HTMLButtonElement>('button')
    .find((b) => b.attributes('aria-label') === name || b.text() === name)
  if (!found) throw new Error(`No button named ${name}`)
  return found
}

/** Opens the menu or popover whose trigger `trigger` selects, as a click on it does. */
export async function openMenu(wrapper: VueWrapper, trigger: string): Promise<void> {
  await wrapper.get(trigger).trigger('click')
  await flushPromises()
}

/** The open menu's item whose text matches `text`. */
export function menuItem(wrapper: VueWrapper, text: string | RegExp): DOMWrapper<HTMLElement> {
  const found = wrapper
    .findAll<HTMLElement>('[role^="menuitem"]')
    .find((item) => (typeof text === 'string' ? item.text() === text : text.test(item.text())))
  if (!found) throw new Error(`No menu item ${String(text)}`)
  return found
}
