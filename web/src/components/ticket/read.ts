// A ticket's read (`keys.ticket`), polled while it has runs so their progress shows. A cached
// answer shows the views at once on reopening; `opening` says whether an answer is the first read
// since the ticket was opened, the one the fields take, so a save is never measured against
// stale fields.

import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, watch } from 'vue'
import { polled, readAgain } from '../../lib/queries'
import { keys, POLL } from '../../lib/queryKeys'
import { loadTicket } from '../../lib/ticket'

export function useTicketRead(repository: () => string, id: () => string, running: () => boolean) {
  const client = useQueryClient()
  const key = computed(() => keys.ticket(repository(), id()))
  const read = useQuery({
    queryKey: key,
    queryFn: () => loadTicket(repository(), id()),
    refetchOnMount: 'always',
    ...polled(POLL.ticket, { ticks: running }),
  })
  let openedAt = 0
  watch([repository, id], () => (openedAt = Date.now()), { immediate: true })
  return {
    read,
    load: () => readAgain(client, key.value, read),
    /** Whether the answer read at `at` is the first since opening; it is so only once. */
    opening: (at: number): boolean => {
      if (!openedAt || at < openedAt) return false
      openedAt = 0
      return true
    },
  }
}
