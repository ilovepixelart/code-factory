// Browser Back closes the topmost overlay (CF-1272). An open overlay holds one history entry on the
// page's own address; it is taken off again however the overlay closes, so one Back is never
// spent on a stale entry. A dialog closed by Escape, its backdrop or a button pops its entry with
// `history.back()`; a Back that finds an overlay open closes it instead of leaving the page.

import { computed, getCurrentInstance, onBeforeUnmount, ref, type WritableComputedRef } from 'vue'

export interface Overlay {
  /** Close the overlay without touching history: its entry is already gone. */
  close: () => void
}

export interface Held extends Overlay {
  id: number
}

const MARK = 'codeFactoryOverlay'
let last = 0
// The overlays holding an entry, the topmost last.
const held: Held[] = []
// The overlays that opened while an entry was still being popped: their entry is pushed once it is.
let waiting: Held[] = []
let popping = 0
let settlers: (() => void)[] = []
let listening = false

function settle(): void {
  if (popping > 0) return
  for (const entry of waiting) push(entry)
  waiting = []
  const done = settlers
  settlers = []
  for (const resolve of done) resolve()
}

function push(entry: Held): void {
  held.push(entry)
  // Spread: the router keeps its own position in the state of the entry.
  history.pushState({ ...(history.state as object | null), [MARK]: entry.id }, '')
}

function onPop(): void {
  if (popping > 0) {
    popping -= 1
    settle()
    return
  }
  held.pop()?.close()
}

/** An overlay opened: it holds one history entry until `leave`. */
export function enter(overlay: Overlay): Held {
  last += 1
  const entry = { ...overlay, id: last }
  if (!listening) {
    listening = true
    addEventListener('popstate', onPop)
  }
  if (popping > 0) waiting.push(entry)
  else push(entry)
  return entry
}

/** An overlay closed, by Back or any other way: its entry is popped unless Back already did. */
export function leave(entry: Held): void {
  waiting = waiting.filter((w) => w !== entry)
  const at = held.indexOf(entry)
  if (at < 0) return
  held.splice(at, 1)
  // Only the entry the page stands on is popped: after a navigation it is no longer under it.
  if (
    at === held.length &&
    (history.state as Record<string, unknown> | null)?.[MARK] === entry.id
  ) {
    popping += 1
    history.back()
  }
}

/** Resolves once no entry is being popped: a navigation sent earlier would land beyond it. */
export function settled(): Promise<void> {
  return popping > 0 ? new Promise((resolve) => settlers.push(resolve)) : Promise.resolve()
}

/** The open state of a Dialog or Sheet (`v-model:open`): it holds a history entry while true, gives
 *  it up as soon as it is set false (so `settled` waits for the pop), and Back sets it false. */
export function useOverlay(): WritableComputedRef<boolean> {
  const shown = ref(false)
  let entry: Held | null = null
  const release = (): void => {
    if (entry) leave(entry)
    entry = null
  }
  if (getCurrentInstance()) onBeforeUnmount(release)
  return computed({
    get: () => shown.value,
    set: (now) => {
      if (now === shown.value) return
      shown.value = now
      if (!now) release()
      else
        entry = enter({
          close: () => {
            entry = null
            shown.value = false
          },
        })
    },
  })
}
