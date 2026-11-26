// CF-364: one board column (docs/ui.md, The kanban): its count against its work-in-progress
// limit, folding, lanes named in every column with a drag group of their own, and a drop sent as a
// move with the list's new order while the board is held.

import { flushPromises, mount } from '@vue/test-utils'
import Sortable from 'sortablejs'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { STAGES, type Card, type Column } from '@/lib/board'
import { clear } from '@/lib/notice'
import { answer, goldenBoard, memoryRouter, spiedBoard, stubFetch } from '../../support/board'
import { present } from '../../support/present'
import BoardColumn from '@/components/BoardColumn.vue'

const board = goldenBoard()
const spec = board.columns.spec

type Lanes = [string, Record<Column, Card[]>][]

function lanesOf(cards: Card[]): Lanes {
  const names = [...new Set(cards.map((c) => c.repository))]
  return names.map((name) => [
    name,
    Object.fromEntries(
      STAGES.map((s) => [s, s === 'spec' ? cards.filter((c) => c.repository === name) : []]),
    ) as Record<Column, Card[]>,
  ])
}

async function column(
  props: Partial<{
    cards: Card[]
    total: number
    limit: number | undefined
    collapsed: boolean
    lanes: Lanes | null
    stage: Column
  }> = {},
) {
  const { live, provide } = spiedBoard(board)
  const router = memoryRouter()
  await router.push('/tickets')
  const wrapper = mount(BoardColumn, {
    props: {
      stage: 'spec',
      cards: spec,
      total: spec.length,
      limit: undefined,
      collapsed: false,
      lanes: null,
      today: board.today,
      ...props,
    },
    global: { plugins: [router], provide, stubs: { CardMenu: true } },
    attachTo: document.body,
  })
  return { wrapper, live }
}

const sortableOf = (list: Element) => present(Sortable.get(list as HTMLElement), 'its sortable')
const groupOf = (list: Element) => (sortableOf(list).option('group') as { name: string }).name

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

describe('the column header', () => {
  // The column's stage reads as its glyph in the stage's colour, beside the column's name.
  test('the_column_header_draws_its_stage_glyph', async () => {
    const { wrapper } = await column()

    const glyph = wrapper.get('h2 svg[data-shape]')
    expect([glyph.attributes('data-shape'), glyph.classes()]).toEqual([
      'ring',
      expect.arrayContaining(['text-chart-7']),
    ])
    wrapper.unmount()
  })

  // CF-494: a column at its narrowest leaves 118 px for its description, which 17 characters fit;
  // CF-1205: each says what puts a ticket in it.
  test('every_column_description_fits_its_narrowest_header', async () => {
    const shown: Record<string, string> = {}
    for (const stage of STAGES) {
      const { wrapper } = await column({ stage, cards: [], total: 0 })
      shown[stage] = wrapper.get('h2 > span.truncate').text()
      wrapper.unmount()
    }

    expect(shown).toStrictEqual({
      spec: 'No branch yet',
      build: 'On a branch',
      review: 'Pull request open',
      merged: 'On main',
    })
    for (const text of Object.values(shown)) expect(text.length).toBeLessThanOrEqual(17)
  })

  test('a_column_without_a_limit_counts_its_cards', async () => {
    const { wrapper } = await column()

    expect(wrapper.get('h2 > span.tabular-nums').text()).toBe('4')
    expect(wrapper.attributes('data-over-limit')).toBeUndefined()
  })

  test('a_column_with_a_limit_shows_its_total_against_it', async () => {
    const { wrapper } = await column({ total: 3, limit: 3 })

    expect(wrapper.get('h2 > span.tabular-nums').text()).toBe('3/3')
    expect(wrapper.attributes('data-over-limit')).toBeUndefined()
    expect(wrapper.attributes('aria-description')).toBeUndefined()
  })

  test('a_column_over_its_limit_says_so', async () => {
    const { wrapper } = await column({ total: 4, limit: 3 })

    expect(wrapper.get('h2 > span.tabular-nums').text()).toBe('4/3')
    expect(wrapper.attributes('data-over-limit')).toBe('')
    expect(wrapper.attributes('aria-description')).toBe('over its work-in-progress limit')
  })

  test('the_column_name_folds_and_opens_the_column', async () => {
    const { wrapper } = await column({ collapsed: true })
    const name = wrapper.get('#column-spec')

    await name.trigger('click')

    expect(name.attributes('aria-expanded')).toBe('false')
    expect(wrapper.attributes('data-collapsed')).toBe('')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  test('an_open_column_says_it_is_expanded', async () => {
    const { wrapper } = await column()

    expect(wrapper.get('#column-spec').attributes('aria-expanded')).toBe('true')
    expect(wrapper.attributes('data-collapsed')).toBeUndefined()
  })
})

describe('the cards', () => {
  test('without_lanes_the_column_is_one_list_in_the_tickets_group', async () => {
    const { wrapper } = await column()
    const lists = wrapper.findAll('ul[data-stage="spec"]')

    expect(lists).toHaveLength(1)
    expect(lists[0]?.findAll('li[data-ticket]').map((li) => li.attributes('data-ticket'))).toEqual([
      'AB-1',
      'AB-2',
      'CF-1',
      'CF-3',
    ])
    expect(groupOf(present(lists[0], 'the list').element)).toBe('tickets')
  })

  test('each_lane_is_named_with_its_count_and_drags_in_a_group_of_its_own', async () => {
    const { wrapper } = await column({ lanes: lanesOf(spec) })
    const lanes = wrapper.findAll('section[data-lane]')

    expect(lanes.map((lane) => lane.get('h3').text())).toEqual(['second2', 'sample2'])
    expect(lanes.map((lane) => groupOf(lane.get('ul').element))).toEqual(['lane-0', 'lane-1'])
    expect(
      lanes.map((lane) =>
        lane.findAll('li[data-ticket]').map((li) => li.attributes('data-ticket')),
      ),
    ).toEqual([
      ['AB-1', 'AB-2'],
      ['CF-1', 'CF-3'],
    ])
  })
})

describe('dragging a card', () => {
  test('a_drag_holds_the_board', async () => {
    const { wrapper, live } = await column()

    present(
      sortableOf(wrapper.get('ul').element).options.onStart,
      'onStart',
    )({} as Sortable.SortableEvent)

    expect(live.hold).toHaveBeenCalledWith(true)
  })

  test('a_drop_sends_a_move_with_the_new_order_and_refreshes_before_releasing_the_board', async () => {
    const sent = stubFetch(() => answer({ notice: 'Moved CF-1', undo: null }))
    const { wrapper, live } = await column()
    const list = wrapper.get('ul').element
    const last = present(list.querySelector<HTMLElement>('li[data-ticket="CF-1"]'), 'CF-1')
    list.insertBefore(last, list.firstChild)

    present(
      sortableOf(list).options.onEnd,
      'onEnd',
    )({
      item: last,
      from: list,
      to: list,
      oldIndex: 2,
      newIndex: 0,
    } as unknown as Sortable.SortableEvent)
    await flushPromises()

    expect(sent).toEqual([
      {
        method: 'POST',
        url: '/api/tickets/sample/CF-1/move',
        body: {
          stage: 'spec',
          order: ['sample/CF-1', 'second/AB-1', 'second/AB-2', 'sample/CF-3'],
        },
      },
    ])
    expect(live.refresh).toHaveBeenCalledWith({ force: true, beforeApply: expect.any(Function) })
    expect(live.hold.mock.calls).toEqual([[false]])
  })

  test('a_drop_names_the_ticket_in_the_address_percent_encoded', async () => {
    const sent = stubFetch(() => answer({ notice: '', undo: null }))
    const card = { ...present(spec[0], 'a card'), repository: 'r#x', id: 'CF 7' }
    const { wrapper } = await column({ cards: [card, ...spec.slice(1)] })
    const list = wrapper.get('ul').element
    const moved = present(list.querySelector<HTMLElement>('li[data-ticket="CF 7"]'), 'CF 7')
    list.appendChild(moved)

    present(
      sortableOf(list).options.onEnd,
      'onEnd',
    )({
      item: moved,
      from: list,
      to: list,
      oldIndex: 0,
      newIndex: 3,
    } as unknown as Sortable.SortableEvent)
    await flushPromises()

    expect(sent.map((s) => s.url)).toEqual(['/api/tickets/r%23x/CF%207/move'])
  })

  test('a_card_put_back_releases_the_board_without_a_move', async () => {
    const sent = stubFetch(() => answer({}))
    const { wrapper, live } = await column()
    const list = wrapper.get('ul').element

    present(
      sortableOf(list).options.onEnd,
      'onEnd',
    )({
      item: list.children[1],
      from: list,
      to: list,
      oldIndex: 1,
      newIndex: 1,
    } as unknown as Sortable.SortableEvent)
    await flushPromises()

    expect(sent).toEqual([])
    expect(live.hold.mock.calls).toEqual([[false]])
  })
})

describe('the Merged column (CF-1077)', () => {
  const twelve = (stage: Column): Card[] =>
    Array.from({ length: 12 }, (_, n) => ({
      ...present(spec[0], 'a card'),
      id: `CF-${String(n + 1)}`,
      stage,
    }))
  const ids = (wrapper: Awaited<ReturnType<typeof column>>['wrapper']) =>
    wrapper.findAll('[data-ticket]').map((c) => c.attributes('data-ticket'))

  // CF-1077-R1: CF-1 to CF-12 read newest first.
  test('merged_lists_newest_first', async () => {
    const { wrapper } = await column({ stage: 'merged', cards: twelve('merged'), total: 12 })

    expect(ids(wrapper).slice(0, 3)).toEqual(['CF-12', 'CF-11', 'CF-10'])
  })

  // CF-1077-R2: ten show, then "Show 2 more"; pressed, all twelve and "Show fewer".
  test('merged_shows_its_ten_newest_and_the_rest_on_asking', async () => {
    const { wrapper } = await column({ stage: 'merged', cards: twelve('merged'), total: 12 })
    const more = () => wrapper.findAll('button').find((b) => b.text().startsWith('Show'))

    expect(ids(wrapper)).toHaveLength(10)
    expect(ids(wrapper).at(-1)).toBe('CF-3')
    expect(more()?.text()).toBe('Show 2 more')
    await more()?.trigger('click')
    expect(ids(wrapper)).toHaveLength(12)
    expect(more()?.text()).toBe('Show fewer')
  })

  // CF-1077-R3: twelve Spec cards all show, with no Show control.
  test('other_columns_list_every_card', async () => {
    const { wrapper } = await column({ stage: 'spec', cards: twelve('spec'), total: 12 })

    expect(ids(wrapper)).toHaveLength(12)
    expect(wrapper.findAll('button').some((b) => b.text().startsWith('Show'))).toBe(false)
  })
})
