// @vitest-environment happy-dom
// CF-316: the shortcut sheet lists every shortcut, the command menu says it is expanded only
// while it lists options, and Copied shows only after the link was written to the clipboard
// (docs/ui.md).

import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { INLINE, menuItem, openMenu } from '../test/overlay'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { notice } from '../lib/notice'
import { answer, goldenBoard, memoryRouter, provideBoard, stubFetch } from '../test/board'
import { present } from '../test/present'
import CommandMenu from './CommandMenu.vue'
import ShortcutSheet from './ShortcutSheet.vue'
import TicketCard from './TicketCard.vue'

const board = goldenBoard()

const provided = provideBoard(board)

const firstCard = () =>
  present(
    Object.values(board.columns).find((cards) => cards.length > 0)?.[0],
    'a card on the board',
  )

const mountCard = (card: ReturnType<typeof firstCard>) =>
  mount(TicketCard, {
    props: { card, stage: card.stage, today: board.today },
    global: { stubs: INLINE, plugins: [memoryRouter()], provide: provided },
  })

// A component left mounted keeps its timers: the command menu's debounced search would send its
// archive read into a later test's stub.
enableAutoUnmount(afterEach)

// The command menu reads the saved views when it opens.
beforeEach(() => {
  stubFetch(() => answer([]))
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the keyboard and the menus', () => {
  test('the_shortcut_sheet_lists_new_ticket', async () => {
    const sheet = mount(ShortcutSheet, { global: { stubs: INLINE } })
    ;(sheet.vm as unknown as { open: () => void }).open()
    await flushPromises()
    const rows = sheet.findAll('dt').map((dt) => dt.text())
    const keys = sheet.findAll('dd').map((dd) => dd.text())

    expect(rows).toContain('New ticket')
    expect(keys[rows.indexOf('New ticket')]).toBe('n')
  })

  test('the_command_menu_is_expanded_only_with_options', async () => {
    const menu = mount(CommandMenu, {
      global: { stubs: INLINE, plugins: [memoryRouter()], provide: provided },
    })
    ;(menu.vm as unknown as { open: () => void }).open()
    await flushPromises()
    const field = menu.get('input[role="combobox"]')

    await field.setValue('Tickets')
    const listing = field.attributes('aria-expanded')
    await field.setValue('zz-nothing-matches-zz')

    expect(listing).toBe('true')
    expect(field.attributes('aria-expanded')).toBe('false')
  })

  test('copied_shows_only_after_the_link_is_written', async () => {
    const card = firstCard()
    vi.stubGlobal('navigator', { clipboard: undefined })
    const menu = mountCard(card)
    await openMenu(menu, '[data-js-menu]')
    const copy = () => menuItem(menu, /Copy link|Copied/)

    await copy().trigger('click')
    await flushPromises()

    expect(copy().text()).toBe('Copy link')
    expect(notice.error).toBe(true)
    expect(notice.text).toContain(`/tickets/${card.repository}/${card.id}`)
  })

  test('duplicate_announces_the_copy_with_its_id', async () => {
    const card = firstCard()
    const sent = stubFetch(() => answer({ repository: card.repository, id: 'CF-77' }))
    const menu = mountCard(card)
    await openMenu(menu, '[data-js-menu]')

    await menuItem(menu, 'Duplicate').trigger('click')
    await flushPromises()

    expect(sent.map((s) => [s.method, s.url.endsWith('/duplicate')])).toEqual([['POST', true]])
    expect([notice.text, notice.error]).toEqual([`Duplicated ${card.id} as CF-77`, false])
  })
})

describe('the card right-click menu', () => {
  const ACTIONS = ['Move to', 'Priority', 'Copy link', 'Duplicate', 'Archive', 'Delete']

  async function rightClick(view: ReturnType<typeof mountCard>): Promise<MouseEvent> {
    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    view.get('[data-js-card-body]').element.dispatchEvent(event)
    await flushPromises()
    return event
  }

  const menuNamed = (view: ReturnType<typeof mountCard>, name: string) =>
    view.findAll('[role="menu"]').filter((menu) => menu.attributes('aria-label') === name)

  test('a_right_click_on_a_card_opens_a_menu_of_its_actions_instead_of_the_browsers', async () => {
    const card = firstCard()
    const view = mountCard(card)

    const event = await rightClick(view)
    const menus = menuNamed(view, `Actions for ${card.id}`)
    const items = present(menus[0], 'the open menu')
      .findAll('[role^="menuitem"]')
      .map((item) => item.text())

    expect([menus.length, event.defaultPrevented]).toEqual([1, true])
    expect(items).toEqual(ACTIONS)
  })

  test('the_right_click_menu_and_the_button_menu_list_the_same_actions', async () => {
    const card = firstCard()
    const view = mountCard(card)
    await openMenu(view, '[data-js-menu]')
    const button = menuItems(view)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    await rightClick(view)

    expect(button).toEqual(ACTIONS)
    expect(menuItems(view)).toEqual(ACTIONS)
  })

  test('duplicate_in_the_right_click_menu_sends_the_cards_duplicate', async () => {
    const card = firstCard()
    const sent = stubFetch(() => answer({ repository: card.repository, id: 'CF-78' }))
    const view = mountCard(card)
    await rightClick(view)

    await menuItem(view, 'Duplicate').trigger('click')
    await flushPromises()

    expect(sent.map((s) => [s.method, s.url.endsWith('/duplicate')])).toEqual([['POST', true]])
    expect(notice.text).toBe(`Duplicated ${card.id} as CF-78`)
  })
})

function menuItems(view: ReturnType<typeof mountCard>): string[] {
  return view.findAll('[role^="menuitem"]').map((item) => item.text())
}
