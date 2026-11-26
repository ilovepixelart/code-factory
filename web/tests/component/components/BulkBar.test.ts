// CF-364: the bulk bar acts on every chosen card in one request; the selection empties once the
// board took it, stays when it refused, and its controls are disabled while it runs (docs/ui.md).

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { clear, notice } from '@/lib/notice'
import { chosen, clearSelection } from '@/lib/selection'
import { answer, spiedBoard, stubFetch } from '../../support/board'
import { present } from '../../support/present'
import BulkBar from '@/components/BulkBar.vue'
import { INLINE, menuItem, openMenu } from '../../support/overlay'

function bar() {
  const { live, provide } = spiedBoard()
  return { bar: mount(BulkBar, { global: { provide, stubs: INLINE } }), live }
}

const button = (wrapper: VueWrapper, name: string) =>
  present(
    wrapper.findAll('button').find((b) => b.text() === name),
    name,
  )

beforeEach(() => {
  chosen.add('sample/CF-1')
  chosen.add('second/CF-9')
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearSelection()
  clear()
})

describe('the bulk bar', () => {
  test('the_bar_counts_the_chosen_cards', () => {
    const { bar: wrapper } = bar()

    expect(wrapper.text()).toContain('2 selected')
  })

  test('move_to_sends_every_chosen_card_to_the_stage_and_empties_the_selection', async () => {
    const sent = stubFetch(() => answer({ notice: 'Moved 2', undo: 't-1' }))
    const { bar: wrapper, live } = bar()

    await openMenu(wrapper, 'button[aria-haspopup="menu"]:not([aria-expanded="true"])')
    await menuItem(wrapper, 'Review').trigger('click')
    await flushPromises()

    expect(sent).toEqual([
      {
        method: 'POST',
        url: '/api/tickets/bulk',
        body: { tickets: ['sample/CF-1', 'second/CF-9'], stage: 'review' },
      },
    ])
    expect(chosen.size).toBe(0)
    expect(live.refresh).toHaveBeenCalledTimes(1)
  })

  test('priority_sets_the_priority_of_every_chosen_card', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const { bar: wrapper } = bar()

    const [, priority] = wrapper.findAll('button[aria-haspopup="menu"]')
    await present(priority, 'Priority').trigger('click')
    await flushPromises()
    await menuItem(wrapper, 'Urgent').trigger('click')
    await flushPromises()

    expect(sent.map((s) => s.body)).toEqual([
      { tickets: ['sample/CF-1', 'second/CF-9'], priority: 'urgent' },
    ])
  })

  test('a_label_is_added_to_every_chosen_card_and_the_field_empties', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const { bar: wrapper } = bar()

    await wrapper.get('input[name="label"]').setValue('ui')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sent.map((s) => s.body)).toEqual([
      { tickets: ['sample/CF-1', 'second/CF-9'], label: 'ui' },
    ])
    expect((wrapper.get('input[name="label"]').element as HTMLInputElement).value).toBe('')
  })

  test('a_blank_label_sends_nothing', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const { bar: wrapper } = bar()

    await wrapper.get('input[name="label"]').setValue('   ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sent).toEqual([])
  })

  test('archive_archives_every_chosen_card', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const { bar: wrapper } = bar()

    await button(wrapper, 'Archive').trigger('click')
    await flushPromises()

    expect(sent.map((s) => s.body)).toEqual([
      { tickets: ['sample/CF-1', 'second/CF-9'], archived: 'true' },
    ])
  })

  test('a_refused_change_keeps_the_selection_and_the_label_and_shows_why', async () => {
    stubFetch(() => answer({ detail: 'CF-9 is archived' }, 409))
    const { bar: wrapper } = bar()

    await wrapper.get('input[name="label"]').setValue('ui')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect([...chosen]).toEqual(['sample/CF-1', 'second/CF-9'])
    expect((wrapper.get('input[name="label"]').element as HTMLInputElement).value).toBe('ui')
    expect(notice.text).toBe('CF-9 is archived')
  })

  test('the_actions_are_disabled_while_a_change_is_sent', async () => {
    let reply: (response: Response) => void = () => undefined
    stubFetch(() => new Promise<Response>((resolve) => (reply = resolve)))
    const { bar: wrapper } = bar()

    await button(wrapper, 'Archive').trigger('click')
    const during = button(wrapper, 'Archive').attributes('disabled')
    reply(answer({ notice: '', undo: null }))
    await flushPromises()

    expect(during).toBeDefined()
    expect(button(wrapper, 'Archive').attributes('disabled')).toBeUndefined()
  })

  test('clear_selection_empties_it_without_a_request', async () => {
    const sent = stubFetch(() => answer({}))
    const { bar: wrapper } = bar()

    await wrapper.get('button[aria-label="Clear selection"]').trigger('click')

    expect(chosen.size).toBe(0)
    expect(sent).toEqual([])
  })
})
