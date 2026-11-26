// Driving shadcn-vue's form controls in a test as a person does.

import { flushPromises, type DOMWrapper, type VueWrapper } from '@vue/test-utils'

/** What `get` answers: a wrapper of an element that is there. */
type Found<T extends Element = Element> = Omit<DOMWrapper<T>, 'exists'>

/** VeeValidate checks a form 5 ms after a change or a submit (its debounced schema validation)
 *  before the submit handler runs or a refusal shows: a test waits that out, then settles. */
export async function validated(): Promise<void> {
  await new Promise((done) => setTimeout(done, 10))
  await flushPromises()
}

/** Type a tag into a tags input's box and press Enter, which adds it. */
export async function addTag(box: Found, text: string): Promise<void> {
  await box.setValue(text)
  await box.trigger('keydown', { key: 'Enter' })
  await flushPromises()
}

/** The tags a tags input holds, in order. */
export const tagsOf = (box: Found): string[] =>
  [...(box.element.parentElement?.querySelectorAll('[data-reka-collection-item] span') ?? [])].map(
    (tag) => tag.textContent.trim(),
  )

/** Open a date picker from its button and pick the first day of the month it shows; the day
 *  picked, as the ISO date the board stores. The calendar is teleported to the body. */
export async function pickDay(button: Found): Promise<string> {
  await button.trigger('click')
  await flushPromises()
  const day = document.querySelector<HTMLElement>(
    '[data-reka-calendar-cell-trigger]:not([data-outside-view])',
  )
  if (!day) throw new Error('The date picker shows no day to pick')
  const value = day.dataset.value ?? ''
  // A day is a <button>. The app teleports the calendar out of the form; a test that renders
  // teleports in place (test/overlay.ts INLINE) has it inside, where its click would submit.
  const hold = (event: Event): void => {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
  document.addEventListener('submit', hold, { capture: true })
  day.click()
  await flushPromises()
  document.removeEventListener('submit', hold, { capture: true })
  return value
}

/** The control a label names through its `for`, the label found by the start of its words. */
export function labelled(within: Found | VueWrapper, label: string): Found<HTMLElement> {
  const named = within.findAll('label').find((l) => l.text().startsWith(label))
  const target = named?.attributes('for')
  if (!target) throw new Error(`No label starts with ${label}`)
  return within.get<HTMLElement>(`[id="${target}"]`)
}

/** Set a control as a person does: tick a checkbox or switch, type a number and leave the field,
 *  or type or choose a value. */
export async function enter(control: Found<HTMLElement>, value: string | boolean): Promise<void> {
  const role = control.attributes('role')
  if (role === 'checkbox' || role === 'switch') {
    if ((control.attributes('aria-checked') === 'true') !== value) await control.trigger('click')
  } else if (role === 'spinbutton') {
    ;(control.element as HTMLInputElement).value = String(value)
    await control.trigger('input')
    await control.trigger('blur')
  } else await control.setValue(value)
}
