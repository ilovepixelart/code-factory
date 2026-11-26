// @vitest-environment happy-dom
// CF-1210: every overlay has a title, Close, and the same footer order (docs/ui.md, Overlays).

import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test } from 'vitest'
import { settled } from '../lib/overlayHistory'
import { answer, confirm } from '../lib/confirm'
import { draftOf } from '../lib/roster'
import AgentForm from './AgentForm.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import ConnectionForm from './ConnectionForm.vue'
import MemoryForm from './MemoryForm.vue'
import ShortcutSheet from './ShortcutSheet.vue'

afterEach(() => {
  answer(false)
  document.body.innerHTML = ''
})
// Registered last, so it runs first: each test's components go before the page is emptied.
enableAutoUnmount(afterEach)

const dialog = (): HTMLElement | null =>
  document.querySelector<HTMLElement>('[role="dialog"], [role="alertdialog"]')
const escape = (): void => {
  document.activeElement?.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
  )
}
const button = (text: string): HTMLButtonElement | undefined =>
  [...(dialog()?.querySelectorAll('button') ?? [])].find((b) => b.textContent.trim() === text)

async function shortcuts() {
  const wrapper = mount(ShortcutSheet, { attachTo: document.body })
  ;(wrapper.vm as unknown as { open: () => void }).open()
  await flushPromises()
  return wrapper
}

// The answer, in a box: an async function returning the promise itself would wait for it.
async function asking(text = 'CF-1 Fix it') {
  mount(ConfirmDialog, { attachTo: document.body })
  const asked = confirm(text)
  await flushPromises()
  return { asked }
}

describe('the dialogs', () => {
  test('the shortcut sheet is a dialog named by its title, and Close closes it', async () => {
    await shortcuts()
    const shown = dialog()
    const title = shown?.getAttribute('aria-labelledby') ?? ''
    const named = document.getElementById(title)?.textContent

    button('Close')?.click()
    await flushPromises()

    expect([named, dialog()]).toEqual(['Keyboard shortcuts', null])
  })

  test('escape_closes_the_shortcut_sheet', async () => {
    await shortcuts()

    escape()
    await flushPromises()

    expect(dialog()).toBeNull()
  })

  test('the_sheet_lists_each_shortcut_with_its_keys', async () => {
    await shortcuts()
    const rows = [...(dialog()?.querySelectorAll('dt') ?? [])].map((dt) => [
      dt.textContent,
      [...(dt.nextElementSibling?.querySelectorAll('[data-slot=kbd]') ?? [])].map(
        (k) => k.textContent,
      ),
    ])

    expect(rows).toContainEqual(['New ticket', ['n']])
    expect(rows).toContainEqual(['Go to Sessions', ['g', 's']])
    expect(rows).toContainEqual(['Go to Tickets', ['g', 't']])
  })

  // The sheet lists every shortcut under the group it works in, in a fixed order.
  test('the_sheet_groups_every_shortcut_by_where_it_works', async () => {
    await shortcuts()
    const groups = [...(dialog()?.querySelectorAll('section') ?? [])].map((section) => [
      section.querySelector('h3')?.textContent,
      [...section.querySelectorAll('dt')].map((dt) => dt.textContent),
    ])

    expect(groups.map(([heading]) => heading)).toEqual(['Everywhere', 'Go to', 'Ticket', 'Inbox'])
    expect(groups[1]?.[1]).toEqual(
      expect.arrayContaining(['Go to Inbox', 'Go to Archive', 'Go to Agents', 'Go to Team']),
    )
    expect(groups[2]?.[1]).toEqual(['Start agent', 'Run checks', 'Edit the title'])
  })

  test('the confirm dialog is an alert dialog with Cancel before Delete and Cancel focused', async () => {
    await asking()
    const shown = dialog()
    const buttons = [...(shown?.querySelectorAll('button') ?? [])].map((b) => b.textContent.trim())

    expect([
      shown?.getAttribute('role'),
      buttons,
      document.activeElement?.textContent.trim(),
    ]).toEqual(['alertdialog', ['Cancel', 'Delete'], 'Cancel'])
    expect(shown?.textContent).toContain('CF-1 Fix it')
  })

  // Asked from the Archive as from the board, so it names no place the ticket leaves.
  test('the_confirm_asks_to_delete_the_ticket_wherever_it_is', async () => {
    await asking()

    expect(
      dialog()?.querySelector('[data-slot="alert-dialog-description"]')?.textContent.trim(),
    ).toBe('Delete CF-1 Fix it? Undo in the notice that follows brings it back.')
  })

  test('cancel_answers_no', async () => {
    const { asked } = await asking()
    button('Cancel')?.click()
    expect(await asked).toBe(false)
  })

  test('escape_answers_no', async () => {
    const { asked } = await asking()
    escape()
    expect(await asked).toBe(false)
  })

  // A dialog asked from a menu item that is gone once it closes gives the keyboard to the menu's
  // button, as a card's Actions menu Delete does.
  test('cancel_returns_focus_to_the_menu_button_the_question_came_from', async () => {
    document.body.innerHTML =
      '<button id="actions" type="button">Actions for CF-1</button>' +
      '<div role="menu" aria-labelledby="actions"><div role="menuitem" tabindex="-1">Delete</div></div>'
    document.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    const { asked } = await asking()
    document.querySelector('[role="menu"]')?.remove()

    button('Cancel')?.click()
    await asked
    await flushPromises()

    expect(document.activeElement?.id).toBe('actions')
  })

  test('delete_answers_yes_and_closes', async () => {
    const { asked } = await asking()
    button('Delete')?.click()
    await flushPromises()
    expect([await asked, dialog()]).toEqual([true, null])
  })
})

describe('the form footers', () => {
  const common = { submit: 'Save it', error: '', busy: false }
  const footer = (wrapper: ReturnType<typeof mount>) =>
    wrapper
      .findAll('form > [data-slot="field-group"] > [data-slot="field"]:last-child button')
      .map((b) => [b.text(), b.attributes('type')])

  test('every form puts Cancel on the left and the primary button on the right', () => {
    const forms = [
      mount(AgentForm, {
        props: {
          ...common,
          name: 'Add',
          start: draftOf(null),
          runtimes: ['claude'],
          gaps: {},
          roles: ['spec'],
          connections: [],
          models: {},
          history: [],
          now: 0,
        },
      }),
      mount(ConnectionForm, {
        props: {
          ...common,
          name: 'Add',
          start: { name: '', kind: 'lm-studio', base_url: '', key_env: '' },
          kinds: [],
        },
      }),
      mount(MemoryForm, {
        props: {
          ...common,
          name: 'Add',
          start: { kind: 'lesson', statement: '', why: '', source: '', guard: '' },
        },
      }),
    ]
    expect(forms.map(footer)).toEqual(
      forms.map(() => [
        ['Cancel', 'button'],
        ['Save it', 'submit'],
      ]),
    )
  })
})

// CF-1272: an open overlay holds one history entry, so Back closes it and Escape leaves none behind.
describe('the overlays and history', () => {
  const marked = () => (history.state as Record<string, unknown> | null)?.codeFactoryOverlay != null

  test('back_closes_an_open_overlay_and_leaves_no_entry', async () => {
    history.pushState(null, '')
    await shortcuts()
    const held = marked()

    history.back()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await flushPromises()

    expect([held, dialog(), marked()]).toEqual([true, null, false])
  })

  test('closing_the_overlay_pops_its_entry_once', async () => {
    history.pushState(null, '')
    await shortcuts()

    escape()
    await settled()
    await flushPromises()

    expect([marked(), dialog()]).toEqual([false, null])
  })
})
