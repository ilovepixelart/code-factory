// The board's view model as `/api/board` answers it.

import type { AtWork } from '../generated/AtWork'

export const STAGES = ['spec', 'build', 'review', 'merged'] as const
/** A board column (CF-828). */
export type Column = (typeof STAGES)[number]
/** A column, or `released`: a ticket a release note names, off the board. */
export type Stage = Column | 'released'

/** Ticket types, the first a new ticket's default. */
export const TYPES = ['feature', 'bug', 'refactor', 'upgrade', 'hotfix', 'docs'] as const

/** What a stage left to the evidence means, on hover wherever a stage is chosen (CF-1089). */
export const EVIDENCE_STAGE_HINT = "Set by the board from the ticket's evidence"

export const STAGE_LABELS: Record<Stage, string> = {
  spec: 'Spec',
  build: 'Build',
  review: 'Review',
  merged: 'Merged',
  released: 'Released',
}

/** Each column's dot colour, a hue of its own from the theme's chart colours: Spec violet, Build
 *  blue, Review yellow, Merged green; a released ticket, off the board, is muted. */
export const STAGE_DOT: Record<Stage, string> = {
  spec: 'bg-chart-7',
  build: 'bg-chart-1',
  review: 'bg-chart-4',
  merged: 'bg-chart-6',
  released: 'bg-muted-foreground',
}

/** The same hues as text colours, for the stage glyph drawn in `currentColor`. */
export const STAGE_TONE: Record<Stage, string> = {
  spec: 'text-chart-7',
  build: 'text-chart-1',
  review: 'text-chart-4',
  merged: 'text-chart-6',
  released: 'text-muted-foreground',
}

// Shown whole in a column header at its narrowest: 16 characters at most (CF-494).
export const STAGE_HINTS: Record<Stage, string> = {
  spec: 'No branch yet',
  build: 'On a branch',
  review: 'Pull request open',
  merged: 'On main',
  released: 'In release notes',
}

export const PRIORITIES = ['urgent', 'high', 'medium', 'low'] as const

interface Run {
  id: string
  agent?: string
  started_at?: number
  stage: Stage
  iteration: number
  loop: boolean
  max_iterations: number
  /** Which of several attempts at the ticket's Build it is; 0 for a single run (CF-1112). */
  attempt: number
}

interface SessionChip {
  session_id: string
  state: 'working' | 'blocked' | 'idle' | 'ended'
}

export interface Pull {
  state: string
  review?: string
  ci: string
  /** The CI outcome without the board's own status, when it differs from `ci`. */
  other_ci?: string
  draft?: boolean
  conflict?: boolean
  head: string
  url: string
  at: string
  since?: string
  /** The lines it adds and removes and the files it changes, when GitHub counted them. */
  additions?: number
  deletions?: number
  changed_files?: number
}

export interface Card {
  id: string
  title: string
  type: string
  branch: string
  repository: string
  repository_path: string
  declared: string
  stage: Stage
  evidence_stage: Stage
  description: string
  labels: string[]
  priority: string
  assignee: string
  due: string
  due_date: string | null
  blocked: string
  archived: boolean
  rank: number
  stage_since: string
  parent: string
  checklist: [number, number]
  open_questions: number
  sessions: SessionChip[]
  runs: Run[]
  /** The session subagents at work on it, oldest run first (CF-1184). */
  subagents: AtWork[]
  due_state: '' | 'overdue' | 'soon'
  days_in_column: number | null
  links: { open_blockers: string[]; children: number; children_done: number } | null
  check: { passed: boolean; commit: string } | null
  pull: Pull | null
  spent: number
  /** A cost of `spent` is the board's estimate; absent when none is (CF-1216). */
  spent_estimated?: boolean
  budget: number | null
  halted: string
  /** What holds it in its column: its first missing required evidence, null when none (CF-489). */
  hold: { stage: Stage; detail: string; summary?: string } | null
  /** While its latest run's usage limit holds it: when it starts again, epoch seconds. */
  limited_until: number | null
  queue?: string
  /** With `queue` next: the open pull request its text likely overlaps (CF-1453). */
  overlap?: string
  holder?: string
  checks_configured?: boolean
  delivery_event?: {
    kind: 'ship_started' | 'ship_pushed' | 'ship_failed' | 'pull_request' | 'merge_failed'
    at: number | null
    retry_at: number | null
    /** A failure's reason, in the words it was recorded with. */
    reason?: string
  }
}

export type FilterGroup = 'type' | 'priority' | 'label' | 'assignee' | 'repository'

export interface Board {
  today: string
  columns: Record<Column, Card[]>
  /** Each folder that could not be read: its repository, its file relative to it, the absolute
   * path and why. */
  problems: { repository: string; file: string; path: string; reason: string }[]
  totals: Record<Column, number>
  limits: Partial<Record<Column, number>>
  options: Record<FilterGroup, string[]>
}

/** How many merged cards the board shows before it is asked for the rest (CF-1077). */
export const MERGED_SHOWN = 10

/** The run of digits that ends `text`, or an empty string. */
export function trailingDigits(text: string): string {
  let start = text.length
  while (start > 0 && text.charAt(start - 1) >= '0' && text.charAt(start - 1) <= '9') start -= 1
  return text.slice(start)
}

/** Cards newest first: by repository, then the number in the id, highest first (CF-1077). */
export function newestFirst(cards: Card[]): Card[] {
  const number = (id: string) => Number(trailingDigits(id))
  return [...cards].sort(
    (a, b) => a.repository.localeCompare(b.repository) || number(b.id) - number(a.id),
  )
}

/** A card's place in the queue in words: `<agent> working`, `Next up` (with the pull request it likely overlaps) or `Held: <reason>`;
 * empty when the board has none. */
/** A pull request's number, the last part of its address. */
export function pullNumber(url: string): string {
  return url.split('/').at(-1) ?? ''
}

export function queueWords(card: Pick<Card, 'holder' | 'queue' | 'overlap'>): string {
  if (card.holder !== undefined) return `${card.holder} working`
  if (card.queue === undefined) return ''
  if (card.queue !== 'next') return `Held: ${card.queue}`
  return card.overlap ? `Next up, ${card.overlap}` : 'Next up'
}
