// What waits on the owner, kept current for the sidebar's count and the tab title: polled every
// few seconds and after each inbox change. When the count grows while the tab is hidden, one
// desktop notification says what arrived; a page's first count only sets the baseline. A browser
// asks for permission only after a gesture: the first click or key press asks, once.

import { useQuery } from '@tanstack/vue-query'
import { useTitle } from '@vueuse/core'
import { ref, toValue, watch, type InjectionKey, type MaybeRefOrGetter, type Ref } from 'vue'
import { ask } from './actions'
import { polled } from './queries'
import { keys, POLL } from './queryKeys'
import { loadText, saveText } from './storage'

const NOTIFY = 'codeFactoryNotify'

export interface Attention {
  count: Ref<number>
  latest: Ref<string>
  refresh: () => Promise<void>
}

export const ATTENTION: InjectionKey<Attention> = Symbol('attention')

/** The tab title a page claims while it is open, such as the Team page's `(2) Team` (CF-1162);
 *  empty leaves the title to the inbox count and the page's name. */
export const pageTitle = ref('')

/** The tab title: the page's claim, else the inbox count and the page's name, then the product's
 *  name, so tabs of the board tell apart (WCAG 2.4.2). */
function tabTitle(claimed: string, page: string, count: number): string {
  const named = claimed || page
  const lead = claimed || count === 0 ? '' : `(${String(count)}) `
  return lead + (named ? `${named} · code-factory` : 'code-factory')
}

/** Whether desktop notifications are on: allowed by the browser and not switched off here. */
export function notifying(): boolean {
  return (
    'Notification' in window && loadText(NOTIFY) !== 'off' && Notification.permission === 'granted'
  )
}

/** Switch desktop notifications, asking the browser first; remembered per browser. */
export async function setNotifying(on: boolean): Promise<void> {
  if (!('Notification' in window)) {
    saveText(NOTIFY, 'off')
    return
  }
  if (on && Notification.permission !== 'granted') await Notification.requestPermission()
  saveText(NOTIFY, on && Notification.permission === 'granted' ? 'on' : 'off')
}

/** Whether a new count deserves a desktop notification: it grew since the last count the page saw
 *  (never for the first), while the tab is hidden and notifications are on. */
export function shouldNotify(
  known: number | null,
  count: number,
  hidden: boolean,
  enabled: boolean,
): boolean {
  return known !== null && count > known && hidden && enabled
}

function notify(count: number, latest: string): void {
  const note = new Notification(`${String(count)} wait${count === 1 ? 's' : ''} on you`, {
    body: latest,
    tag: 'code-factory-inbox',
  })
  note.onclick = () => {
    window.focus()
    window.location.assign('/inbox')
  }
}

function askOnFirstGesture(): void {
  if (!('Notification' in window) || loadText(NOTIFY) === 'off') return
  if (Notification.permission !== 'default') return
  const once = (): void => {
    document.removeEventListener('click', once, true)
    document.removeEventListener('keydown', once, true)
    void Notification.requestPermission()
  }
  document.addEventListener('click', once, true)
  document.addEventListener('keydown', once, true)
}

/** What waits on the owner; `page` names the page shown, for the tab title. */
export function useAttention(page: MaybeRefOrGetter<string> = ''): Attention {
  const count = ref(0)
  const latest = ref('')
  let known: number | null = null
  const title = useTitle(null, { restoreOnUnmount: false })

  // Polled while the tab is hidden too: that is when a notification is due.
  const query = useQuery({
    queryKey: keys.inboxCount,
    queryFn: ({ signal }) => ask<{ count: number; latest: string }>('/api/inbox/count', signal),
    ...polled(POLL.inboxCount, { background: true }),
  })
  watch(query.data, (answer) => {
    if (!answer) return
    if (shouldNotify(known, answer.count, document.hidden, notifying())) {
      notify(answer.count, answer.latest)
    }
    known = answer.count
    count.value = answer.count
    latest.value = answer.latest
    title.value = tabTitle(pageTitle.value, toValue(page), answer.count)
  })
  watch(
    [pageTitle, () => toValue(page)],
    ([claimed, shown]) => (title.value = tabTitle(claimed, shown, count.value)),
  )
  askOnFirstGesture()
  return {
    count,
    latest,
    refresh: async () => {
      await query.refetch()
    },
  }
}
