// A ticket's keys press its own controls (s Start agent, r Run checks, e the title), and only when
// the person is not typing, holds no modifier, has not just pressed g, and no other dialog is open.

import { afterEach, expect, test, vi } from 'vitest'
import { sequence } from '@/lib/keys'
import { onTicketKey } from '@/lib/ticketKeys'

function ticket(): { root: HTMLElement; start: () => number; checks: () => number } {
  document.body.innerHTML = `
    <div id="ticket">
      <textarea data-shortcut="title"></textarea>
      <button data-shortcut="start">Start agent</button>
      <button data-shortcut="checks">Run checks</button>
      <input id="field" />
    </div>`
  const root = present(document.getElementById('ticket'))
  const count = (name: string) => {
    let n = 0
    root.querySelector(`[data-shortcut="${name}"]`)?.addEventListener('click', () => (n += 1))
    return () => n
  }
  return { root, start: count('start'), checks: count('checks') }
}

function press(
  root: HTMLElement,
  key: string,
  init: KeyboardEventInit = {},
  at: Element = document.body,
) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  Object.defineProperty(event, 'target', { value: at })
  onTicketKey(event, root)
  return event
}

afterEach(() => {
  sequence.gAt = 0
  vi.useRealTimers()
  document.body.innerHTML = ''
})

test('s_starts_the_agent_r_runs_the_checks_and_e_edits_the_title', () => {
  const { root, start, checks } = ticket()

  press(root, 's')
  press(root, 'r')
  press(root, 'e')

  expect([start(), checks(), document.activeElement?.getAttribute('data-shortcut')]).toEqual([
    1,
    1,
    'title',
  ])
})

test('a_key_typed_in_a_field_or_with_a_modifier_presses_nothing', () => {
  const { root, start } = ticket()

  press(root, 's', {}, present(root.querySelector('#field')))
  press(root, 's', { metaKey: true })
  press(root, 's', { ctrlKey: true })
  press(root, 's', { altKey: true })

  expect(start()).toBe(0)
})

test('the_key_after_g_belongs_to_go_to', () => {
  const { root, start } = ticket()

  sequence.gAt = Date.now()
  press(root, 's')

  expect(start()).toBe(0)
})

test('a_disabled_or_missing_control_is_not_pressed', () => {
  const { root, start } = ticket()
  root.querySelector<HTMLButtonElement>('[data-shortcut="start"]')?.setAttribute('disabled', '')
  root.querySelector('[data-shortcut="checks"]')?.remove()

  const r = press(root, 'r')
  press(root, 's')

  expect([start(), r.defaultPrevented]).toEqual([0, false])
})

test('a_dialog_other_than_the_tickets_own_holds_the_keys', () => {
  const { root, start } = ticket()
  const other = document.createElement('div')
  other.setAttribute('role', 'dialog')
  other.dataset.state = 'open'
  document.body.append(other)

  press(root, 's')
  other.append(root)
  press(root, 's')

  expect(start()).toBe(1)
})

function present<T>(value: T | null): T {
  if (value === null) throw new Error('the fixture lost an element')
  return value
}
