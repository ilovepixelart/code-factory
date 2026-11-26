// The Flow page's merged pull requests (CF-1203): how many a day, and which of them did not hold
// (CF-1215).

import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import { FLOW } from './analytics'
import { ArrowLeft02Icon, CheckListIcon, Link01Icon } from '@hugeicons/core-free-icons'
import type { Icon } from './icon'
import type { Merged } from './metrics'

/** Merges a day over the range, to one decimal. */
export function perDay(count: number, since: number, now: number): number {
  const days = Math.max((now - since) / 86_400, 1 / 24)
  return Math.round((count / days) * 10) / 10
}

/** A way a merge did not hold: reverted later, the cause of a later ticket, or merged without the
 *  board's checks having passed on its head. */
export type Held = 'reverted' | 'fixed' | 'unchecked'

/** Each way, in the page's order: its tile's title and icon, and Recently merged's hint and its
 *  empty line while narrowed to it. */
export const HELD: { key: Held; title: string; icon: Icon; hint: string; none: string }[] = [
  {
    key: 'reverted',
    title: 'Reverted',
    icon: ArrowLeft02Icon,
    hint: 'reverted by a later commit',
    none: 'No merge in this range was reverted',
  },
  {
    key: 'fixed',
    title: 'Needed a fix',
    icon: Link01Icon,
    hint: "named by a later ticket's caused_by",
    none: 'No merge in this range is the cause of a later ticket',
  },
  {
    key: 'unchecked',
    title: 'Unchecked',
    icon: CheckListIcon,
    hint: "merged without the board's checks having passed on the head",
    none: "Every merge in this range had passed the board's checks",
  },
]

/** The Flow address listing the merges that did not hold in the way `held` names, all of them
 *  without one: every other key of `query` kept, from the list's first page. */
export function heldList(
  query: LocationQuery,
  held: Held | null,
): { path: string; query: LocationQueryRaw } {
  const next: LocationQueryRaw = { ...query }
  delete next.merged_page
  delete next.held
  if (held) next.held = held
  return { path: FLOW, query: next }
}

/** Whether `merge` did not hold in the way `kind` names. */
export function notHeld(merge: Merged, kind: Held): boolean {
  if (kind === 'reverted') return merge.reverted
  if (kind === 'fixed') return merge.fixes.length > 0
  return merge.checks !== 'passed'
}

/** `part` of `whole` as a whole percent, half up; 0 of nothing is 0. */
export function share(part: number, whole: number): number {
  return whole > 0 ? Math.round((part * 100) / whole) : 0
}
