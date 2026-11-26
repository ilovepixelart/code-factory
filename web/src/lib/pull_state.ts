// The one label a pull request carries on a card and a Sessions row (CF-1217), read from what the
// board already holds: its pull request record and its own checks record; no call to GitHub.

import type { Card } from './board'
import { statusVariant, type BadgeVariant } from './status_tone'

export type PullState =
  | 'draft'
  | 'open'
  | 'checks failing'
  | 'checks running'
  | 'conflict'
  | 'approved'
  | 'merged'
  | 'closed'

/** The shown words, sentence case, and the Badge variant of each state (its word's in `statusVariant`). */
export const PULL_STATES: Record<PullState, { words: string; variant: BadgeVariant }> =
  Object.fromEntries(
    (
      [
        'merged',
        'closed',
        'conflict',
        'checks failing',
        'checks running',
        'draft',
        'approved',
        'open',
      ] as const
    ).map((s) => [s, { words: s.charAt(0).toUpperCase() + s.slice(1), variant: statusVariant(s) }]),
  ) as Record<PullState, { words: string; variant: BadgeVariant }>

/**
 * The state of a card's pull request, the first that holds of: merged, closed unmerged, in
 * conflict, its checks failing, its checks running, a draft, approved, open. The label says the
 * checks fail only by the pull request's CI outcome without the board's status, and only while
 * the board holds no record of its own: the board's failed checks are the card's own text
 * (CF-1318), so one failure is said once and the same way on every card. They run while the other checks are pending beside the board's passed record,
 * or, with no board record, while any check is pending (the board's record holds finished runs
 * only). Null with no pull request.
 */
export function pullState(card: Pick<Card, 'pull' | 'check'>): PullState | null {
  const { pull, check } = card
  if (pull === null) return null
  if (pull.state === 'merged') return 'merged'
  if (pull.state === 'closed') return 'closed'
  if (pull.state !== 'open') return null
  if (pull.conflict) return 'conflict'
  const others = pull.other_ci ?? pull.ci
  if (!check && others === 'failed') return 'checks failing'
  if (check ? others === 'pending' : pull.ci === 'pending') return 'checks running'
  if (pull.draft) return 'draft'
  return pull.review === 'approved' ? 'approved' : 'open'
}
