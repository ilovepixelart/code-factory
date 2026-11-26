import type { Pull } from './board'

// A pull request's size, as GitHub counts it: writing a change costs ever less while reading it
// does not, so the board says how much there is to review. Past LARGE_PULL_LINES changed lines a
// review stops catching defects well, and the change reads as large.

export const LARGE_PULL_LINES = 400

/** The counts a size is read from: a card's pull, or an Inbox merge item's size. */
export type PullCounts = Pick<Pull, 'additions' | 'deletions' | 'changed_files'>

export interface PullSize {
  added: number
  removed: number
  files: number
  lines: number
  large: boolean
}

/** The size of `pull`, or null when GitHub gave no count of its lines. */
export function pullSize(pull: PullCounts | null | undefined): PullSize | null {
  if (pull?.additions === undefined || pull.deletions === undefined) return null
  const lines = pull.additions + pull.deletions
  return {
    added: pull.additions,
    removed: pull.deletions,
    files: pull.changed_files ?? 0,
    lines,
    large: lines > LARGE_PULL_LINES,
  }
}
