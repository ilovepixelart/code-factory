// @vitest-environment happy-dom
// CF-364: a column's menu sets or clears its work-in-progress limit (docs/ui.md, How much runs
// at once); a refusal shows and keeps the menu open, and the controls are disabled while it runs.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { clear, notice } from '../lib/notice'
import { answer, spiedBoard, stubFetch } from '../test/board'
import { present } from '../test/present'
import ColumnMenu from './ColumnMenu.vue'
import { INLINE, openMenu } from '../test/overlay'

async function menuOf(limit: number | undefined) {
  const { live, provide } = spiedBoard()
  const menu = mount(ColumnMenu, {
    props: { stage: 'build', limit },
    global: { provide, stubs: INLINE },
    attachTo: document.body,
  })
  await openMenu(menu, 'button[aria-label="Column menu for Build"]')
  const opened = () => menu.find('[data-slot="popover-content"]').exists()
  return { menu, live, opened }
}

// The limit is a number field: what is typed lands when the field is left, as a person's click on
// Set limit leaves it.
async function typeLimit(menu: ReturnType<typeof mount>, text: string): Promise<void> {
  const box = menu.get('[role="spinbutton"]')
  ;(box.element as HTMLInputElement).value = text
  await box.trigger('input')
  await box.trigger('blur')
}

const button = (menu: ReturnType<typeof mount>, name: string) =>
  present(
    menu.findAll('button').find((b) => b.text() === name),
    name,
  )

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

describe('the column menu', () => {
  test('the_field_shows_the_columns_limit_and_follows_it', async () => {
    const { menu } = await menuOf(4)
    const field = menu.get('[role="spinbutton"]').element as HTMLInputElement
    const shown = field.value

    await menu.setProps({ limit: undefined })

    expect(shown).toBe('4')
    expect(field.value).toBe('')
  })

  test('set_limit_sends_the_typed_number', async () => {
    const sent = stubFetch(() => answer({ notice: 'Build limit 3', undo: null }))
    const { menu, live } = await menuOf(undefined)

    await typeLimit(menu, '3')
    await menu.get('form').trigger('submit')
    await flushPromises()

    expect(sent).toEqual([{ method: 'PUT', url: '/api/columns/build/limit', body: { limit: 3 } }])
    expect(live.refresh).toHaveBeenCalledTimes(1)
  })

  test('set_limit_with_an_empty_field_clears_the_limit', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const { menu } = await menuOf(4)

    await typeLimit(menu, '')
    await menu.get('form').trigger('submit')
    await flushPromises()

    expect(sent.map((s) => s.body)).toEqual([{ limit: null }])
  })

  test('a_limit_that_is_not_a_whole_number_goes_as_typed_for_the_board_to_judge', async () => {
    const sent = stubFetch(() => answer({ detail: 'a limit is a whole number' }, 400))
    const { menu } = await menuOf(undefined)

    await typeLimit(menu, '2.5')
    await menu.get('form').trigger('submit')
    await flushPromises()

    expect(sent.map((s) => s.body)).toEqual([{ limit: 2.5 }])
  })

  test('clear_sends_no_limit_whatever_is_typed', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const { menu } = await menuOf(4)

    await typeLimit(menu, '7')
    await button(menu, 'Clear').trigger('click')
    await flushPromises()

    expect(sent.map((s) => s.body)).toEqual([{ limit: null }])
  })

  test('a_saved_limit_closes_the_menu', async () => {
    stubFetch(() => answer({ notice: 'Build limit 3', undo: null }))
    const { menu, opened } = await menuOf(undefined)

    await typeLimit(menu, '3')
    await menu.get('form').trigger('submit')
    await flushPromises()

    expect(opened()).toBe(false)
  })

  test('a_refused_limit_shows_why_and_keeps_the_menu_open', async () => {
    stubFetch(() => answer({ detail: 'a limit is a whole number' }, 400))
    const { menu, opened } = await menuOf(undefined)

    await typeLimit(menu, '2.5')
    await menu.get('form').trigger('submit')
    await flushPromises()

    expect(notice.text).toBe('a limit is a whole number')
    expect(notice.error).toBe(true)
    expect(opened()).toBe(true)
  })

  test('both_buttons_are_disabled_while_a_limit_is_sent', async () => {
    let reply: (response: Response) => void = () => undefined
    stubFetch(() => new Promise<Response>((resolve) => (reply = resolve)))
    const { menu } = await menuOf(undefined)

    await typeLimit(menu, '3')
    await menu.get('form').trigger('submit')
    const buttons = () =>
      ['Set limit', 'Clear'].map((name) => button(menu, name).attributes('disabled') !== undefined)
    const during = buttons()
    // A refusal keeps the menu open, so its buttons are there to read once the answer came.
    reply(answer({ detail: 'Refused' }, 409))
    await flushPromises()
    const after = buttons()

    expect(during).toEqual([true, true])
    expect(after).toEqual([false, false])
  })
})
