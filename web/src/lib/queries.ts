// The app's TanStack Query client and the options a polled read shares. Keys and intervals are
// in queryKeys.ts.

import {
  keepPreviousData,
  QueryClient,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/vue-query'
import {
  computed,
  onScopeDispose,
  shallowRef,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from 'vue'
import { ask, Refused } from './actions'

/** The client the app provides. A read that fails is not retried: what the page showed stays
 *  until the next poll or change reads it again, and a read that stays failed says so. Nothing is
 *  read again on focus or reconnect unless the read polls (`polled`). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false },
    },
  })
}

interface Refetchable {
  isFetching: Ref<boolean>
  refetch: () => Promise<unknown>
}

/** Read the query under `key` again now, as after a change. A read under way is cancelled first:
 *  one sent before the change must not stand for after it, and Query's own `cancelRefetch` spares
 *  it while the query has no answer yet. */
export async function readAgain(
  client: QueryClient,
  key: QueryKey,
  query: Refetchable,
): Promise<void> {
  if (query.isFetching.value) await client.cancelQueries({ queryKey: key, exact: true })
  await query.refetch()
}

interface Polled {
  /** Whether the poll runs now; it reads at once when this turns true. Default: always. */
  ticks?: MaybeRefOrGetter<boolean>
  /** Keep polling while the tab is hidden, as the Inbox count does to notify. */
  background?: boolean
}

/** The options of a read polled every `every` milliseconds (a value of `POLL`) while `ticks`. */
export function polled(every: number | false, { ticks = true, background = false }: Polled = {}) {
  const on = computed(() => every !== false && toValue(ticks))
  return {
    refetchInterval: computed(() => (on.value ? every : false)),
    refetchIntervalInBackground: background,
    refetchOnWindowFocus: on,
  }
}

/** A one-time read of `path` under `key` whose every answer, a cached one first, is handed to
 *  `apply`; a refusal leaves what was applied. */
export function useApplied<T>(key: QueryKey, path: string, apply: (answer: T) => void) {
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => ask<T>(path, signal) })
  watch(
    query.data,
    (answer) => {
      if (answer) apply(answer)
    },
    { immediate: true },
  )
  return query
}

/** Whether a read the shown pages hold got no answer from the board at its latest try, and the
 *  oldest answer still shown from such a read (epoch milliseconds), null when none is shown. A
 *  refusal is an answer: the board gave its reason. */
export interface Unanswered {
  failing: boolean
  since: number | null
}

export function useUnanswered(): Readonly<Ref<Unanswered>> {
  const cache = useQueryClient().getQueryCache()
  const scan = (): Unanswered => {
    const failing = cache
      .getAll()
      .filter(
        (q) =>
          q.getObserversCount() > 0 &&
          q.state.status === 'error' &&
          !(q.state.error instanceof Refused),
      )
    const shown = failing
      .filter((q) => q.state.data !== undefined)
      .map((q) => q.state.dataUpdatedAt)
    return { failing: failing.length > 0, since: shown.length ? Math.min(...shown) : null }
  }
  const state = shallowRef(scan())
  const stop = cache.subscribe(() => {
    const next = scan()
    if (next.failing !== state.value.failing || next.since !== state.value.since) state.value = next
  })
  onScopeDispose(stop)
  return state
}

/** A page's polled read under `key`: its query, its last answer (kept while later reads fail) and
 *  a read now. It stops while the tab is hidden and reads again as the tab shows, unless it says
 *  it must act while hidden (`background`). */
export function usePolledRead<T>(
  key: MaybeRefOrGetter<QueryKey>,
  read: (signal: AbortSignal) => Promise<T>,
  every: number | false,
  { ticks = true, background = false }: Polled = {},
) {
  const client = useQueryClient()
  const queryKey = computed(() => toValue(key))
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => read(signal),
    // A read that does not tick is not read at all, as a usage read with no session shown.
    enabled: computed(() => toValue(ticks)),
    // A new key (another page of the list) keeps the last answer shown until its own arrives.
    placeholderData: keepPreviousData,
    ...polled(every, { ticks, background }),
  })
  return {
    query,
    data: computed(() => query.data.value ?? null),
    refresh: () => readAgain(client, queryKey.value, query),
  }
}
