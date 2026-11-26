// The board's data: `/api/board` read as the app opens and after a change, and polled with its
// ETag only while the tab is seen and a page that shows the board follows it or the board has not
// answered (CF-1235): each read builds the whole board on the server, an unchanged one too. The
// header shows connecting, live or reconnecting. The reads are one TanStack Query (`keys.board`):
// a later read cancels an earlier one, and holding the board cancels the read under way.

import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref, watch, type InjectionKey, type Ref } from 'vue'
import { reasonOf, Refused, request } from './actions'
import type { Board } from './board'
import { BUILD_HEADER, noteBuild } from './build'
import { refusalText } from './notice'
import { polled } from './queries'
import { keys, POLL } from './queryKeys'

export type LiveState = 'connecting' | 'live' | 'reconnecting'

export interface Live {
  board: Readonly<Ref<Board | null>>
  state: Readonly<Ref<LiveState>>
  /** The board's reason for refusing this browser's reads (403: not signed in), '' while it answers. */
  refused: Readonly<Ref<string>>
  /** Why the latest read failed other than by a refusal, in words, '' once a read answers. */
  failed: Readonly<Ref<string>>
  /** Read the board now, as after a change, instead of at the next poll. */
  refresh: (options?: Refresh) => Promise<void>
  /** Hold the board still, as while a card is dragged: no poll is read, none applied. */
  hold: (still: boolean) => void
  /** Poll the board while the calling page's scope lives: for a page that shows the board. */
  follow: () => void
}

interface Refresh {
  /** Read even while the board is held. */
  force?: boolean
  /** Run as the answer arrives, before it is applied, in the same task. */
  beforeApply?: () => void
}

/** The live board, shared by the shell, the board page and the command menu. */
export const BOARD: InjectionKey<Live> = Symbol('board')

/** What the board query keeps: the board and the ETag it was sent with. */
interface Tagged {
  board: Board
  tag: string
}

/** A read of the board it refused, with the reason it gave. */
class BoardRefused extends Error {
  readonly reason: string
  constructor(reason: string) {
    super(reason)
    this.reason = reason
  }
}

/** Whether a read starts: never while the board is held, as during a drag, unless forced. */
export function readsNow(held: boolean, force: boolean): boolean {
  return !held || force
}

export function useBoard(): Live {
  const client = useQueryClient()
  const held = ref(false)
  const followers = ref(0)
  // Run by the next read as its answer arrives; each read takes it as it starts.
  let beforeApply: (() => void) | undefined

  async function read(signal: AbortSignal): Promise<Tagged> {
    let before = beforeApply
    beforeApply = undefined
    const settle = (): void => {
      before?.()
      before = undefined
    }
    try {
      const kept = client.getQueryData<Tagged>(keys.board)
      const response = await request(
        '/api/board',
        kept?.tag ? { headers: { 'If-None-Match': kept.tag }, signal } : { signal },
      )
      noteBuild(response.headers.get(BUILD_HEADER))
      if (response.status === 304 && kept) return kept
      if (response.status === 403) {
        throw new BoardRefused(reasonOf(await response.json().catch(() => null), 403))
      }
      if (response.status !== 200) {
        const status = response.status
        throw new Refused(reasonOf(await response.json().catch(() => null), status))
      }
      return { board: (await response.json()) as Board, tag: response.headers.get('ETag') ?? '' }
    } finally {
      settle()
    }
  }

  // Whether the latest read answered; set from the query's status below.
  const answered = ref(false)
  const query = useQuery({
    queryKey: keys.board,
    queryFn: ({ signal }) => read(signal),
    // Until it answers, as while this browser is not signed in, every page reads it again.
    ...polled(POLL.board, {
      ticks: () => !held.value && (followers.value > 0 || !answered.value),
    }),
  })
  watch(query.status, (status) => (answered.value = status === 'success'), { immediate: true })

  const board = computed(() => query.data.value?.board ?? null)
  const state = computed<LiveState>(() => {
    if (query.status.value === 'success') return 'live'
    return board.value ? 'reconnecting' : 'connecting'
  })
  // A refusal stands until a read answers; a read that did not reach the board leaves it.
  const refused = ref('')
  const failed = ref('')
  watch([query.status, query.error, query.dataUpdatedAt], () => {
    const error = query.error.value
    if (query.status.value === 'success') {
      refused.value = ''
      failed.value = ''
    } else if (error instanceof BoardRefused) refused.value = error.reason
    else if (error) failed.value = refusalText(error)
  })

  async function refresh({ force = false, beforeApply: before }: Refresh = {}): Promise<void> {
    if (!readsNow(held.value, force)) return
    // A read sent before the change must not stand for after it: Query's own cancelRefetch
    // spares a read under way while the board has no answer yet, so it is cancelled here.
    if (query.isFetching.value) await client.cancelQueries({ queryKey: keys.board })
    beforeApply = before
    await query.refetch()
  }
  function hold(still: boolean): void {
    held.value = still
    if (still) void client.cancelQueries({ queryKey: keys.board })
  }
  function follow(): void {
    followers.value += 1
    if (!query.isFetching.value && !held.value) void query.refetch({ cancelRefetch: false })
    onScopeDispose(() => {
      followers.value -= 1
    })
  }

  return { board, state, refused, failed, refresh, hold, follow }
}
