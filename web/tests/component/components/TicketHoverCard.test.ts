// A ticket id link previews its ticket (title, stage, assignee, labels) on hover and on focus:
// from the live board when the ticket is on it, else from one read of the ticket; the link still
// navigates.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { Card } from '@/lib/board'
import { answer, goldenBoard, memoryRouter, provideBoard, stubFetch } from '../../support/board'
import { INLINE } from '../../support/overlay'
import { present } from '../../support/present'
import TicketHoverCard from '@/components/TicketHoverCard.vue'

const board = goldenBoard()
const OPEN_DELAY_MS = 700

const onBoard = (): Card =>
  present(
    Object.values(board.columns)
      .flat()
      .find((card) => card.labels.length > 0 && card.assignee),
    'a card with labels and an assignee',
  )

function shown(repository: string, ticket: string, router = memoryRouter()) {
  return mount(TicketHoverCard, {
    props: { repository, ticket },
    slots: { default: ticket },
    attrs: { class: 'hover:underline' },
    global: { stubs: INLINE, plugins: [router], provide: provideBoard(board) },
  })
}

async function focus(view: ReturnType<typeof shown>): Promise<void> {
  await view.get('a').trigger('focus')
  vi.advanceTimersByTime(OPEN_DELAY_MS)
  await flushPromises()
}

const content = (view: ReturnType<typeof shown>) => view.find('[data-slot="hover-card-content"]')

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('a ticket id link', () => {
  test('focus_shows_the_preview_of_a_ticket_on_the_board_without_a_read', async () => {
    const card = onBoard()
    const sent = stubFetch(() => answer({}))
    const view = shown(card.repository, card.id)

    await focus(view)
    const preview = content(view)

    expect(sent).toEqual([])
    expect(preview.text()).toContain(card.title)
    expect(preview.get('[data-preview-stage]').text()).toBe(
      { spec: 'Spec', build: 'Build', review: 'Review', merged: 'Merged', released: 'Released' }[
        card.stage
      ],
    )
    expect(preview.find('[data-preview-stage] svg[data-shape]').exists()).toBe(true)
    expect(preview.get('[data-preview-assignee]').text()).toBe(`@${card.assignee}`)
    expect(preview.findAll('[data-preview-label]').map((label) => label.text())).toEqual(
      card.labels,
    )
  })

  test('no_preview_shows_before_the_link_is_hovered_or_focused', () => {
    const card = onBoard()
    const view = shown(card.repository, card.id)

    expect(content(view).exists()).toBe(false)
  })

  test('a_ticket_off_the_board_is_read_once_for_its_preview', async () => {
    const card: Card = { ...onBoard(), id: 'CF-9001', title: 'Archived long ago', labels: [] }
    const sent = stubFetch(() => answer({ card }))
    const view = shown(card.repository, card.id)

    await focus(view)
    await view.get('a').trigger('blur')
    vi.advanceTimersByTime(OPEN_DELAY_MS)
    await focus(view)

    expect(sent.map((s) => s.url)).toEqual([`/api/tickets/${card.repository}/CF-9001`])
    expect(content(view).text()).toContain('Archived long ago')
  })

  test('a_ticket_the_board_does_not_find_says_it_could_not_be_read', async () => {
    stubFetch(() => answer({ detail: 'no such ticket' }, 404))
    const view = shown('code-factory', 'CF-404')

    await focus(view)

    expect(content(view).text()).toBe('CF-404 could not be read')
  })

  test('the_link_still_navigates_to_the_ticket', async () => {
    const card = onBoard()
    const router = memoryRouter()
    await router.push('/team')
    const view = shown(card.repository, card.id, router)

    await view.get('a').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe(`/tickets/${card.repository}/${card.id}`)
    expect(view.get('a').classes()).toContain('hover:underline')
  })
})
