// A card's actions, held by the card so its two menus (the button's and the right-click's) share
// one busy state while a change is sent.

import { computed, inject, ref } from 'vue'
import type { Changed } from '../generated/Changed'
import { act } from './actions'
import type { Card, Stage } from './board'
import { confirm } from './confirm'
import { BOARD } from './live'
import { failed, perform } from './notice'
import { ticketHref } from './ticket'
import { setArchived } from './ticketActions'

export const PRIORITIES = ['urgent', 'high', 'medium', 'low', ''] as const

export function useCardActions(card: () => Card) {
  const live = inject(BOARD)
  const busy = ref(false)
  const copied = ref(false)
  const base = computed(
    () => `/api/tickets/${encodeURIComponent(card().repository)}/${encodeURIComponent(card().id)}`,
  )

  async function run(change: () => Promise<Changed>): Promise<void> {
    busy.value = true
    await perform(change, live?.refresh ?? (() => Promise.resolve()))
    busy.value = false
  }

  const move = (to: Stage) => run(() => act('POST', `${base.value}/move`, { stage: to, order: [] }))
  const prioritise = (priority: string) => run(() => act('PATCH', base.value, { priority }))
  const duplicate = () =>
    run(async () => {
      const copy = await act('POST', `${base.value}/duplicate`)
      const id = card().id
      return { ...copy, notice: copy.id ? `Duplicated ${id} as ${copy.id}` : copy.notice }
    })
  const archive = () => run(() => setArchived(base.value, true))

  async function remove(): Promise<void> {
    if (await confirm(`${card().id} ${card().title}`)) await run(() => act('DELETE', base.value))
  }

  // The menu stays open on Copy link, so it can say Copied.
  async function copyLink(event: Event): Promise<void> {
    event.preventDefault()
    const link = `${location.origin}${ticketHref(card().repository, card().id)}`
    try {
      await navigator.clipboard.writeText(link)
      copied.value = true
    } catch {
      failed(`The link could not be copied: ${link}`)
    }
  }

  return { busy, copied, move, prioritise, duplicate, archive, remove, copyLink }
}

export type CardActions = ReturnType<typeof useCardActions>
