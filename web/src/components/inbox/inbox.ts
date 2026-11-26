import {
  computed,
  inject,
  nextTick,
  reactive,
  ref,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from 'vue'
import { act } from '../../lib/actions'
import type { InboxItem, Section } from '../../lib/metrics'
import { announce, failed, refusalText } from '../../lib/notice'
import { usePaged, type Paged } from '../../lib/paging'
import { ticketHref } from '../../lib/ticket'

/** The address of an inbox item's ticket page. */
export const itemHref = (item: InboxItem): string =>
  ticketHref(item.ticket?.repository ?? '', item.ticket?.id ?? '')

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, summary'
const ROWS = ':scope [data-slot="section-content"] > [data-slot="item-group"] > [role="listitem"]'

/** Where the keyboard was: the heading of the section holding the focused row, and the row's place. */
interface Spot {
  heading: string
  index: number
}

function spotOf(active: Element | null): Spot | null {
  const section = active?.closest('section[aria-labelledby]')
  if (!active || !section) return null
  const rows = [...section.querySelectorAll(ROWS)]
  return {
    heading: section.getAttribute('aria-labelledby') ?? '',
    index: rows.findIndex((row) => row.contains(active)),
  }
}

function place(target: HTMLElement | null | undefined): void {
  if (!target) return
  if (!target.matches(FOCUSABLE)) target.tabIndex = -1
  target.focus()
}

/**
 * Once an acted row has left and focus fell to the page, put it on the row now in its place, else
 * on its section's heading, else on the first heading the page still has.
 */
async function refocus(spot: Spot | null): Promise<void> {
  await nextTick()
  const active = document.activeElement
  if (active && active !== document.body && active.isConnected) return
  const heading = document.getElementById(spot?.heading ?? '')
  const row = heading?.closest('section')?.querySelectorAll(ROWS)[spot?.index ?? -1]
  place(
    row?.querySelector<HTMLElement>(FOCUSABLE) ??
      heading ??
      document.querySelector<HTMLElement>('#inbox-region h2') ??
      document.getElementById('inbox-region'),
  )
}

/**
 * Actions keyed by what they act on: a key is busy while its action runs and keeps the refusal
 * of its last attempt, which shows under its item; `changed` runs after every attempt, and a
 * refusal whose key it no longer lists (`listed`) shows in the page's notice instead, after the
 * item's name (`named`, read before the action, while the item is listed).
 */
export function useKeyedActions(
  changed: () => Promise<void>,
  listed: (key: string) => boolean,
  named: (key: string) => string,
) {
  const busy = ref(new Set<string>())
  const errors = reactive<Record<string, string>>({})

  async function run(
    key: string,
    method: 'POST' | 'PUT' | 'PATCH',
    path: string,
    body?: object,
  ): Promise<boolean> {
    const name = named(key)
    const spot = spotOf(document.activeElement)
    busy.value.add(key)
    delete errors[key]
    let done = false
    try {
      announce(await act(method, path, body))
      done = true
    } catch (error) {
      errors[key] = refusalText(error)
    } finally {
      busy.value.delete(key)
    }
    await changed()
    if (done) await refocus(spot)
    const refusal = errors[key]
    if (refusal !== undefined && !listed(key)) failed(`${name}: ${refusal}`)
    return done
  }

  return { busy, errors, run }
}

/** The address of an inbox item's ticket in the API. */
export const ticketApi = (item: InboxItem): string =>
  `/api/tickets/${encodeURIComponent(item.ticket?.repository ?? '')}/${item.ticket?.id ?? ''}`

/** The key a question's answer runs under. */
export const questionKey = (item: InboxItem): string =>
  `question-${String(item.ticket?.repository)}-${String(item.ticket?.id)}-${String(item.question?.document)}-${String(item.question?.index)}`

/**
 * The id of a row a push links to after `#` (CF-761), as
 * the server makes it: a session by its id, a failing default branch by
 * its repository, any other row by its section and ticket, one row per ticket in each.
 */
export const rowId = (section: Section, item: InboxItem): string => {
  if (section === 'sessions') return `sessions-${String(item.session?.session_id)}`
  if (section === 'main') return `main-${String(item.main?.repository)}`
  return `${section}-${String(item.ticket?.repository)}-${String(item.ticket?.id)}`
}

/**
 * The key each section's action runs under: its refusal shows under the item while a refresh
 * lists the key, else in the page's notice.
 */
export const actionKeys = {
  questions: questionKey,
  permissions: (item: InboxItem) => `perm-${String(item.request?.id)}`,
  rules: (item: InboxItem) => `rule-${item.reason}`,
  memory: (item: InboxItem) =>
    `memory-${String(item.memory?.repository)}-${String(item.memory?.id)}`,
  stopped: (item: InboxItem) => `run-${itemHref(item)}`,
  screens: (item: InboxItem) => `screens-${itemHref(item)}`,
  mergeable: (item: InboxItem) => `merge-${itemHref(item)}`,
} satisfies Partial<Record<Section, (item: InboxItem) => string>>

/** What the Inbox page shares with its sections: the clock, its actions and the primary button. */
export interface InboxContext {
  now: Ref<number>
  busy: Ref<Set<string>>
  errors: Record<string, string>
  run: (
    key: string,
    method: 'POST' | 'PUT' | 'PATCH',
    path: string,
    body?: object,
  ) => Promise<boolean>
  primary: (section: Section, index: number) => 'default' | 'secondary'
}

export const INBOX: InjectionKey<InboxContext> = Symbol('inbox')

/** The Inbox page's context, for a section drawn inside it. */
export function useInbox(): InboxContext {
  const context = inject(INBOX)
  if (!context) throw new Error('an Inbox section is drawn only inside the Inbox page')
  return context
}

/** The address key a section's page is held under (`stopped_page`, `stopped_size`). */
export const pagePrefix = (section: Section): string => `${section}_`

/**
 * One page of a section's items (CF-1196), paged in the address under the section's own prefix;
 * `offset` is the index of the page's first item among all of them, which `next_up` names.
 */
export function useSectionPage(
  section: Section,
  items: () => InboxItem[] | null,
): { paged: Paged<InboxItem>; offset: ComputedRef<number> } {
  const paged = usePaged(items, pagePrefix(section))
  return { paged, offset: computed(() => (paged.page.value - 1) * paged.size.value) }
}

/**
 * The element id of an item as the server makes `anchor`, which a
 * push link names after `#`.
 */
export const anchorOf = (section: Section, item: InboxItem): string => {
  if (section === 'questions') return questionKey(item)
  if (section === 'permissions') return actionKeys.permissions(item)
  return rowId(section, item)
}
