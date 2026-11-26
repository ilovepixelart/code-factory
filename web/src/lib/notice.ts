// The page's notice: what a change did, with Undo when it
// can be taken back, or why it was refused; it hides itself after a few seconds.

import { reactive, ref, type Ref } from 'vue'
import type { Changed } from '../generated/Changed'
import { act, Refused, type Answered } from './actions'

const NOTICE_SECONDS = 8

/** A notice's way to what the change made, as "Open CF-12" after a create. */
export interface Follow {
  label: string
  run: () => void
}

export const notice = reactive({
  text: '',
  undo: null as string | null,
  error: false,
  follow: null as Follow | null,
})
let timer: ReturnType<typeof setTimeout> | undefined

function show(text: string, undo: string | null, error: boolean, follow: Follow | null): void {
  Object.assign(notice, { text, undo, error, follow })
  clearTimeout(timer)
  if (text) timer = setTimeout(clear, NOTICE_SECONDS * 1000)
}

/** Show what a change did, with its Undo, as `perform` does after a change; an answer that says
 * nothing clears the earlier notice, which no longer describes the page. `follow` leads to what
 * the change made, offered where no Undo is. */
export function announce(answer: Changed, follow: Follow | null = null): void {
  show(answer.notice, answer.undo, false, follow)
}

/** Show a failure in its own words. */
export function failed(text: string): void {
  show(text, null, true, null)
}

export function clear(): void {
  show('', null, false, null)
}

/** Why a change failed, in words: the server's reason, or that it did not answer. */
export function refusalText(error: unknown): string {
  return error instanceof Refused ? error.message : 'The board did not answer; try again.'
}

/** Show why a change failed. */
export function refused(error: unknown): void {
  show(refusalText(error), null, true, null)
}

/** A change a form or row sends: `busy` while it is sent, `error` its refusal in words. */
export interface Action {
  busy: Ref<boolean>
  error: Ref<string>
  send: (
    method: 'POST' | 'PATCH' | 'DELETE',
    path: string,
    body: object | undefined,
    done: (answer: Answered) => unknown,
  ) => Promise<void>
}

/** Send a change, show what it answered and run `done` with the answer; a refusal is kept in `error` instead. */
export function useAction(): Action {
  const busy = ref(false)
  const error = ref('')
  async function send(
    method: 'POST' | 'PATCH' | 'DELETE',
    path: string,
    body: object | undefined,
    done: (answer: Answered) => unknown,
  ): Promise<void> {
    busy.value = true
    error.value = ''
    try {
      const answer = await act(method, path, body)
      announce(answer)
      await done(answer)
    } catch (failure) {
      error.value = refusalText(failure)
    }
    busy.value = false
  }
  return { busy, error, send }
}

/** Run a change, show what it answered, then let the board refresh; a refusal shows instead. */
export async function perform(
  change: () => Promise<Changed>,
  refresh: () => Promise<void>,
): Promise<boolean> {
  try {
    announce(await change())
    return true
  } catch (error) {
    refused(error)
    return false
  } finally {
    await refresh()
  }
}

/** How many changes have been taken back: a page holding data the board does not, such as the
 * memory, reads again when it moves. */
export const undone = ref(0)

/** Take back the change the notice names. */
export async function undo(refresh: () => Promise<void>): Promise<void> {
  const token = notice.undo
  if (!token) return
  clear()
  await perform(() => act('POST', `/api/undo/${token}`), refresh)
  undone.value++
}
