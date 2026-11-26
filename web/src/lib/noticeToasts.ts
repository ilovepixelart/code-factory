// The page's notice as a toast: what a change did, with Undo when it can be taken back, or why it
// was refused; and the offer to reload once the board runs a newer build. The notice store keeps
// its own timer, so a toast lasts until the store clears it.

import { nextTick, ref, watch, type Ref } from 'vue'
import { toast } from 'vue-sonner'
import { build, UPDATED } from './build'
import { clear, notice, undo } from './notice'
import { chosen } from './selection'

const RELOAD = 'reload'
// A bar holding the bottom edge (the bulk bar, the agents-stopped bar) keeps the toasts above it.
const GAP_PX = 8

// Each notice is a toast of its own: vue-sonner applies a dismissal a frame later, so a toast
// dismissed and shown again under one id would be taken down with the new words in it.
let made = 0
let shown = 0

function show(refresh: () => Promise<void>): void {
  const { text, error, undo: token, follow } = notice
  if (shown) toast.dismiss(shown)
  if (!text) {
    shown = 0
    return
  }
  const id = ++made
  shown = id
  const options = {
    id,
    duration: Number.POSITIVE_INFINITY,
    onDismiss: () => {
      if (shown === id) clear()
    },
  }
  if (error) toast.error(text, options)
  else if (token) {
    toast(text, {
      ...options,
      action: {
        label: 'Undo',
        onClick: () => {
          void undo(refresh)
        },
      },
    })
  } else if (follow) {
    toast(text, { ...options, action: { label: follow.label, onClick: follow.run } })
  } else toast(text, options)
}

/** Show the notice and the reload offer as toasts; the answer is the toasts' distance from the
 *  bottom edge, in pixels, or null where nothing holds that edge. */
export function useNoticeToasts(refresh: () => Promise<void>): Ref<number | null> {
  const lift = ref<number | null>(null)
  watch(
    () => [notice.text, notice.error, notice.undo, notice.follow],
    () => {
      show(refresh)
    },
    { immediate: true },
  )
  watch(
    () => build.stale,
    (stale) => {
      if (!stale) return
      toast(UPDATED, {
        id: RELOAD,
        duration: Number.POSITIVE_INFINITY,
        action: {
          label: 'Reload',
          onClick: () => {
            window.location.reload()
          },
        },
      })
    },
    { immediate: true },
  )
  watch([() => notice.text, () => chosen.size], async () => {
    await nextTick()
    lift.value = bottomLift(window.innerHeight)
  })
  return lift
}

/** How far above the bottom edge the toasts sit: above the highest element that holds that edge
 *  (`data-holds-bottom`: the bulk bar, the agents-stopped bar), or null when none does. */
export function bottomLift(height: number): number | null {
  const tops = [...document.querySelectorAll<HTMLElement>('[data-holds-bottom]')].map(
    (element) => element.getBoundingClientRect().top,
  )
  return tops.length ? height - Math.min(...tops) + GAP_PX : null
}
