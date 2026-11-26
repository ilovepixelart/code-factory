// CF-364: the tickets page's document gestures (docs/ui.md, The kanban): a plain click on a card
// opens its panel, Cmd, Ctrl or Shift and a click chooses it, / acts only while nobody types, and
// pressing on empty board space pans it.

import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { present } from '../../support/present'
import { useBoardGestures, type BoardGestures } from '@/lib/boardGestures'
import { chosen, clearSelection } from '@/lib/selection'

const BOARD = `
  <div data-js-pan id="pan">
    <ul>
      <li data-ticket="CF-1" data-repository="sample">
        <button type="button" data-js-menu aria-expanded="false" id="menu-1">More</button>
        <div data-js-card-body id="body-1">
          <a href="/tickets/sample/CF-1" data-js-card-link id="title-1">Title</a>
          <a href="https://example.test/pr" id="pr-1">PR</a>
          <span id="text-1">Text</span>
          <button type="button" id="control-1">Run</button>
        </div>
        <span id="outside-body-1">Footer</span>
      </li>
      <li data-ticket="CF-2" data-repository="second">
        <button type="button" data-js-menu aria-expanded="false" id="menu-2">More</button>
        <div data-js-card-body><span id="text-2">Text</span></div>
      </li>
    </ul>
    <input id="field" />
    <span id="empty-space">space</span>
  </div>`

function setUp() {
  document.body.innerHTML = BOARD
  const actions = { openPanel: vi.fn(), focusSearch: vi.fn() }
  const made: { gestures?: BoardGestures } = {}
  const host = mount(
    defineComponent({
      setup() {
        made.gestures = useBoardGestures(actions)
        return () => h('div')
      },
    }),
  )
  return { actions, host, gestures: present(made.gestures, 'the gestures') }
}

const el = (id: string): HTMLElement =>
  present(document.querySelector<HTMLElement>(`#${id}`), `#${id}`)

function click(id: string, init: MouseEventInit = {}): MouseEvent {
  const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init })
  el(id).dispatchEvent(event)
  return event
}

function key(key: string, target: Element = document.body, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  target.dispatchEvent(event)
  return event
}

const DIALOG = '<div role="dialog" data-state="open"></div>'

beforeEach(() => {
  clearSelection()
})

afterEach(() => {
  clearSelection()
  document.body.innerHTML = ''
})

describe('opening and choosing cards', () => {
  test('a_plain_click_on_a_card_opens_its_panel', () => {
    const { actions } = setUp()

    const event = click('text-1')

    expect(actions.openPanel).toHaveBeenCalledWith('sample', 'CF-1')
    expect(event.defaultPrevented).toBe(true)
  })

  test('a_plain_click_on_the_card_title_opens_the_panel_instead_of_the_page', () => {
    const { actions } = setUp()

    const event = click('title-1')

    expect(actions.openPanel).toHaveBeenCalledWith('sample', 'CF-1')
    expect(event.defaultPrevented).toBe(true)
  })

  test('a_click_on_another_link_in_a_card_follows_the_link', () => {
    const { actions } = setUp()

    const event = click('pr-1')

    expect(actions.openPanel).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  test('a_middle_click_on_a_card_does_not_open_its_panel', () => {
    const { actions } = setUp()

    click('title-1', { button: 1 })

    expect(actions.openPanel).not.toHaveBeenCalled()
  })

  test('a_click_on_a_card_outside_its_body_does_not_open_its_panel', () => {
    const { actions } = setUp()

    click('outside-body-1')

    expect(actions.openPanel).not.toHaveBeenCalled()
  })

  test('a_cmd_click_chooses_the_card_instead_of_opening_it', () => {
    const { actions } = setUp()

    const event = click('text-1', { metaKey: true })

    expect([...chosen]).toEqual(['sample/CF-1'])
    expect(actions.openPanel).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(true)
  })

  test('a_ctrl_click_and_a_shift_click_each_choose_a_card', () => {
    setUp()

    click('text-1', { ctrlKey: true })
    click('text-2', { shiftKey: true })

    expect([...chosen]).toEqual(['sample/CF-1', 'second/CF-2'])
  })

  test('a_second_cmd_click_on_a_chosen_card_lets_it_go', () => {
    setUp()

    click('text-1', { metaKey: true })
    click('text-1', { metaKey: true })

    expect([...chosen]).toEqual([])
  })

  test('a_cmd_click_on_a_card_control_chooses_the_card_before_the_control', () => {
    setUp()
    const control = vi.fn((event: Event) => {
      event.stopPropagation()
    })
    el('control-1').addEventListener('click', control)

    click('control-1', { metaKey: true })

    expect([...chosen]).toEqual(['sample/CF-1'])
    expect(control).not.toHaveBeenCalled()
  })

  test('a_cmd_click_on_a_card_menu_does_not_choose_the_card', () => {
    setUp()

    click('menu-1', { metaKey: true })

    expect([...chosen]).toEqual([])
  })
})

describe('the board shortcuts', () => {
  test('escape_clears_the_selection', () => {
    setUp()
    click('text-1', { metaKey: true })

    key('Escape')

    expect(chosen.size).toBe(0)
  })

  test('escape_keeps_the_selection_while_a_dialog_is_open', () => {
    setUp()
    click('text-1', { metaKey: true })
    document.body.insertAdjacentHTML('beforeend', DIALOG)

    key('Escape')

    expect([...chosen]).toEqual(['sample/CF-1'])
  })

  test('slash_focuses_the_filter_box', () => {
    const { actions } = setUp()

    const event = key('/')

    expect(actions.focusSearch).toHaveBeenCalledTimes(1)
    expect(event.defaultPrevented).toBe(true)
  })

  test('slash_typed_in_a_field_stays_in_the_field', () => {
    const { actions } = setUp()

    const event = key('/', el('field'))

    expect(actions.focusSearch).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  test('slash_with_cmd_or_ctrl_or_an_open_dialog_does_not_focus_the_filter_box', () => {
    const { actions } = setUp()

    key('/', document.body, { metaKey: true })
    key('/', document.body, { ctrlKey: true })
    document.body.insertAdjacentHTML('beforeend', DIALOG)
    key('/')

    expect(actions.focusSearch).not.toHaveBeenCalled()
  })

  test('the_gestures_stop_with_the_page', () => {
    const { actions, host } = setUp()

    host.unmount()
    key('/')
    click('text-1')

    expect(actions.focusSearch).not.toHaveBeenCalled()
    expect(actions.openPanel).not.toHaveBeenCalled()
  })
})

describe('panning the board', () => {
  function press(id: string, clientX: number, button = 0): PointerEvent {
    const event = new PointerEvent('pointerdown', { bubbles: true, clientX, button })
    Object.defineProperty(event, 'target', { value: el(id) })
    return event
  }
  const move = (clientX: number) =>
    document.dispatchEvent(new PointerEvent('pointermove', { clientX }))

  test('dragging_empty_board_space_sideways_scrolls_the_board_the_other_way', () => {
    const { gestures } = setUp()
    el('pan').scrollLeft = 100

    gestures.panStart(press('empty-space', 300))
    move(260)

    expect(el('pan').scrollLeft).toBe(140)
    expect(el('pan').classList.contains('cursor-grabbing')).toBe(true)
  })

  test('releasing_the_pointer_ends_the_pan', () => {
    const { gestures } = setUp()
    el('pan').scrollLeft = 100
    gestures.panStart(press('empty-space', 300))

    document.dispatchEvent(new PointerEvent('pointerup'))
    move(200)

    expect(el('pan').scrollLeft).toBe(100)
    expect(el('pan').classList.contains('cursor-grabbing')).toBe(false)
  })

  test('pressing_on_a_card_or_a_field_does_not_pan', () => {
    const { gestures } = setUp()
    el('pan').scrollLeft = 100

    gestures.panStart(press('text-1', 300))
    gestures.panStart(press('field', 300))
    move(200)

    expect(el('pan').scrollLeft).toBe(100)
  })

  test('pressing_with_another_button_does_not_pan', () => {
    const { gestures } = setUp()
    el('pan').scrollLeft = 100

    gestures.panStart(press('empty-space', 300, 2))
    move(200)

    expect(el('pan').scrollLeft).toBe(100)
  })
})
