// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import Sortable from 'sortablejs'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h, withDirectives, type PropType } from 'vue'
import { present } from '../test/present'
import { dragging, droppedOrder, vSortable, type Drop, type Sorting } from './sortable'

test('dropped_order_names_each_card', () => {
  const cards = [
    { dataset: { ticket: 'CF-2', repository: 'sample' } },
    { dataset: { ticket: 'CF-1', repository: 'second' } },
    { dataset: { ticket: 'CF-10', repository: 'my repo' } },
  ]

  expect(droppedOrder(cards)).toEqual(['sample/CF-2', 'second/CF-1', 'my repo/CF-10'])
  expect(droppedOrder([])).toEqual([])
})

// CF-364: docs/ui.md (The kanban), a drop is sent with the list's new order, the card stays where
// it was dropped until the server's board arrives, and a lane's lists share a group of their own.
const card = (repository: string, id: string) =>
  h('li', { 'data-ticket': id, 'data-repository': repository, id: `card-${id}` }, id)

const Lists = defineComponent({
  props: { sorting: { type: Object as PropType<Sorting>, required: true } },
  setup(props) {
    return () =>
      h('div', [
        withDirectives(
          h('ul', { 'data-stage': 'brd', id: 'brd' }, [
            card('sample', 'CF-1'),
            card('sample', 'CF-2'),
            card('sample', 'CF-3'),
          ]),
          [[vSortable, props.sorting]],
        ),
        withDirectives(h('ul', { 'data-stage': 'frd', id: 'frd' }, [card('second', 'CF-9')]), [
          [vSortable, props.sorting],
        ]),
      ])
  },
})

function setUp(group = 'tickets') {
  const sorting = { group, start: vi.fn(), drop: vi.fn<(drop: Drop | null) => void>() }
  const lists = mount(Lists, { props: { sorting }, attachTo: document.body })
  const list = (id: string) => present(document.querySelector<HTMLElement>(`#${id}`), `#${id}`)
  const instance = (id: string) => present(Sortable.get(list(id)), `the sortable of #${id}`)
  return { sorting, lists, list, instance }
}

/** Sortable's end of a drag: the item already moved to `to` at `newIndex`, as Sortable leaves it. */
function end(instance: Sortable, fields: Partial<Sortable.SortableEvent>): void {
  present(instance.options.onEnd, 'onEnd')(fields as Sortable.SortableEvent)
}

const ids = (list: HTMLElement) => [...list.children].map((li) => li.id)

afterEach(() => {
  dragging.value = false
  document.body.innerHTML = ''
})

describe('dragging a card', () => {
  // CF-840-R1: a card lifts only after its press is held 250 ms within 5 pixels, mouse or touch.
  test('a_drag_waits_for_a_held_press', () => {
    const { instance } = setUp()
    const options = instance('brd').options

    expect([options.delay, options.delayOnTouchOnly, options.touchStartThreshold]).toEqual([
      250,
      false,
      5,
    ])
  })

  test('a_drag_start_marks_the_board_dragging_and_holds_it', () => {
    const { sorting, instance } = setUp()

    present(instance('brd').options.onStart, 'onStart')({} as Sortable.SortableEvent)

    expect(dragging.value).toBe(true)
    expect(sorting.start).toHaveBeenCalledTimes(1)
  })

  test('a_card_put_back_where_it_was_is_no_drop', () => {
    const { sorting, list, instance } = setUp()
    dragging.value = true

    end(instance('brd'), {
      item: list('brd').children[1] as HTMLElement,
      from: list('brd'),
      to: list('brd'),
      oldIndex: 1,
      newIndex: 1,
    })

    expect(dragging.value).toBe(false)
    expect(sorting.drop).toHaveBeenCalledWith(null)
  })

  test('a_drop_names_the_card_its_new_stage_and_the_new_order_there', () => {
    const { sorting, list, instance } = setUp()
    const moved = present(document.querySelector<HTMLElement>('#card-CF-2'), 'CF-2')
    list('frd').insertBefore(moved, list('frd').firstChild)

    end(instance('brd'), {
      item: moved,
      from: list('brd'),
      to: list('frd'),
      oldIndex: 1,
      newIndex: 0,
    })
    const drop = present(sorting.drop.mock.calls[0]?.[0], 'the drop')

    expect(drop).toMatchObject({
      repository: 'sample',
      id: 'CF-2',
      stage: 'frd',
      order: ['sample/CF-2', 'second/CF-9'],
    })
  })

  test('a_reorder_within_a_column_is_a_drop_in_the_same_stage', () => {
    const { sorting, list, instance } = setUp()
    const moved = present(document.querySelector<HTMLElement>('#card-CF-3'), 'CF-3')
    list('brd').insertBefore(moved, list('brd').firstChild)

    end(instance('brd'), {
      item: moved,
      from: list('brd'),
      to: list('brd'),
      oldIndex: 2,
      newIndex: 0,
    })
    const drop = present(sorting.drop.mock.calls[0]?.[0], 'the drop')

    expect(drop.stage).toBe('brd')
    expect(drop.order).toEqual(['sample/CF-3', 'sample/CF-1', 'sample/CF-2'])
  })

  test('undo_puts_the_card_back_where_it_was_picked_up', () => {
    const { sorting, list, instance } = setUp()
    const moved = present(document.querySelector<HTMLElement>('#card-CF-2'), 'CF-2')
    list('frd').appendChild(moved)
    end(instance('brd'), {
      item: moved,
      from: list('brd'),
      to: list('frd'),
      oldIndex: 1,
      newIndex: 1,
    })

    present(sorting.drop.mock.calls[0]?.[0], 'the drop').undo()

    expect(ids(list('brd'))).toEqual(['card-CF-1', 'card-CF-2', 'card-CF-3'])
    expect(ids(list('frd'))).toEqual(['card-CF-9'])
  })

  test('undo_puts_a_card_taken_from_the_end_back_at_the_end', () => {
    const { sorting, list, instance } = setUp()
    const moved = present(document.querySelector<HTMLElement>('#card-CF-3'), 'CF-3')
    list('frd').appendChild(moved)
    end(instance('brd'), {
      item: moved,
      from: list('brd'),
      to: list('frd'),
      oldIndex: 2,
      newIndex: 1,
    })

    present(sorting.drop.mock.calls[0]?.[0], 'the drop').undo()

    expect(ids(list('brd'))).toEqual(['card-CF-1', 'card-CF-2', 'card-CF-3'])
  })
})

describe('the lists', () => {
  test('a_lane_takes_its_group_and_follows_a_new_one', async () => {
    const { lists, instance } = setUp('lane-0')
    const before = (instance('brd').option('group') as { name: string }).name

    await lists.setProps({ sorting: { group: 'lane-1', start: vi.fn(), drop: vi.fn() } })

    expect(before).toBe('lane-0')
    expect((instance('brd').option('group') as { name: string }).name).toBe('lane-1')
  })

  test('a_drop_goes_to_the_handlers_the_list_holds_now', async () => {
    const { lists, list, instance } = setUp()
    const later = { group: 'tickets', start: vi.fn(), drop: vi.fn() }
    await lists.setProps({ sorting: later })

    end(instance('brd'), {
      item: list('brd').children[0] as HTMLElement,
      from: list('brd'),
      to: list('brd'),
      oldIndex: 0,
      newIndex: 0,
    })

    expect(later.drop).toHaveBeenCalledWith(null)
  })

  test('a_press_on_a_card_menu_does_not_start_a_drag', () => {
    const { instance } = setUp()

    expect(instance('brd').option('filter')).toBe('[data-js-menu]')
  })

  test('a_list_stops_sorting_when_it_leaves_the_page', () => {
    const { lists, list } = setUp()
    const brd = list('brd')

    lists.unmount()

    expect(Sortable.get(brd)).toBeFalsy()
  })
})
