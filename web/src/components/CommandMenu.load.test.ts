// @vitest-environment happy-dom
// The search library is its own chunk, loaded when the menu opens (CF-848 keeps the ranking).

import { flushPromises, mount } from '@vue/test-utils'
import { INLINE } from '../test/overlay'
import { afterEach, expect, test, vi } from 'vitest'
import { STAGES, type Card } from '../lib/board'
import { UPDATED } from '../lib/build'
import { clear, notice } from '../lib/notice'
import { answer, goldenBoard, memoryRouter, provideBoard, stubFetch } from '../test/board'
import { present } from '../test/present'
import CommandMenu from './CommandMenu.vue'

const library = vi.hoisted(() => ({
  gate: Promise.resolve(),
  fail: false,
}))

vi.mock('fuse.js', async (original) => {
  await library.gate
  if (library.fail) throw new Error('Failed to fetch dynamically imported module')
  return original()
})

const golden = goldenBoard()
const template = present(STAGES.flatMap((s) => golden.columns[s])[0], 'a card in the golden board')

function opened() {
  stubFetch(() => answer([]))
  const cards: Card[] = ['Release notes name every ticket', 'Sessions list their runs'].map(
    (title, i) => ({ ...template, repository: 'sample', id: `CF-${String(i + 1)}`, title }),
  )
  const columns = Object.fromEntries(STAGES.map((s) => [s, [] as Card[]])) as typeof golden.columns
  columns[STAGES[0]] = cards
  const menu = mount(CommandMenu, {
    global: {
      stubs: INLINE,
      plugins: [memoryRouter()],
      provide: provideBoard({ ...golden, columns }),
    },
  })
  const open = (menu.vm as unknown as { open: () => Promise<void> }).open()
  return { menu, open }
}

const rows = (menu: ReturnType<typeof mount>) =>
  menu.findAll('[role="option"]').map((option) => option.text())

afterEach(() => {
  clear()
  vi.unstubAllGlobals()
  library.gate = Promise.resolve()
  library.fail = false
})

test('a_failed_library_load_shows_the_reload_notice_and_the_menu_still_matches_text', async () => {
  library.fail = true
  const { menu, open } = opened()
  await open
  await flushPromises()
  await menu.get('input[role="combobox"]').setValue('release')

  expect([notice.text, notice.error, rows(menu)]).toEqual([
    UPDATED,
    true,
    ['CF-1 Release notes name every ticketsample'],
  ])
})

test('a_query_typed_before_the_library_arrives_matches_text_then_ranks_when_it_has', async () => {
  let arrive: () => void = () => undefined
  library.gate = new Promise<void>((resolve) => {
    arrive = resolve
  })
  const { menu, open } = opened()
  await open
  await menu.get('input[role="combobox"]').setValue('SESSIONS list')
  const before = rows(menu)
  await menu.get('input[role="combobox"]').setValue('sesions')
  const misspelt = rows(menu)
  arrive()
  await vi.waitFor(() => {
    expect([...rows(menu)].sort()).toEqual([
      'CF-2 Sessions list their runssample',
      'Go to Sessionspagegs',
    ])
  })

  expect([before, misspelt]).toEqual([['CF-2 Sessions list their runssample'], []])
})
