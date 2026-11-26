// What the Memory and Archive pages read.

import type { Stage } from './board'

export type MemoryKind = 'rule' | 'decision' | 'lesson'
export const MEMORY_KINDS: [MemoryKind, string][] = [
  ['rule', 'Rule'],
  ['decision', 'Decision'],
  ['lesson', 'Lesson'],
]

export interface MemoryRecord {
  repository: string
  id: string
  kind: MemoryKind
  date: string
  source: string
  statement: string
  why: string
  reviewed: string
  guard: string
  guard_state: '' | 'enforced' | 'missing' | 'none'
  loaded: boolean
  /** Every session would load it, but the budget leaves it out (CF-1164). */
  left_out: boolean
  /** The id of the active entry that supersedes it, else empty (CF-1165). */
  superseded_by: string
  /** Where it loads (CF-1166): empty or `core` for every session, `spec`, `build`, `review`, or
   * path globs, comma separated. */
  scope: string
  supersedes: string
  /** Where it loads, in the page's words. */
  loads: string
  /** The characters of its recall line. */
  chars: number
  /** An agent wrote it and it waits for approval (CF-1168). */
  proposed: boolean
  stale: boolean
  incomplete: boolean
  /** The day its review falls due, `YYYY-MM-DD` (CF-1167). */
  review_due: string
  /** Whether its change is on main (CF-1170). */
  filing: 'committed' | 'pending' | 'failed'
  /** The runs that received it, oldest first (CF-1169). */
  received_by: { run: string; ticket_id: string }[]
  /** What it cites that no longer exists (CF-1403). */
  stale_cites?: string[]
  /** No run received it for 30 days (CF-1403). */
  unused?: boolean
  /** How many runs received it and the day of the latest, empty for never (CF-1403). */
  received_count?: number
  last_received?: string
}

export interface RetiredRecord {
  repository: string
  id: string
  kind: MemoryKind
  date: string
  source: string
  statement: string
  why: string
  guard: string
  retired: string
  merged_into: string
}

export interface Found {
  repository: string
  path: string
  snippet: string
  /** The ticket page, `#<entry id>` on this page, a file on GitHub, or empty. */
  open: string
}

/** A consolidation proposal (CF-978), applied through the merge or retire route. */
export interface MemoryProposal {
  repository: string
  action: 'merge' | 'retire'
  id: string
  statement: string
  into?: string
  into_statement?: string
  guard?: string
  reason?: string
}

/** Two active entries on one subject that consolidate flags (CF-1165). */
export interface MemoryPair {
  repository: string
  one: string
  other: string
  one_statement: string
  other_statement: string
  /** The distinctive words both statements hold. */
  terms: string[]
  contradicts: boolean
}

export interface Memory {
  repositories: string[]
  proposals: MemoryProposal[]
  unreviewed: MemoryRecord[]
  rules: MemoryRecord[]
  decisions: MemoryRecord[]
  lessons: MemoryRecord[]
  retired: RetiredRecord[]
  /** What every session loads, before the budget cuts. */
  loaded_chars: number
  ceiling: number
  /** The characters the every-session rules and decisions take past the ceiling. */
  rules_over?: number
  /** The every-session entries the budget leaves out. */
  left_out: { repository: string; id: string }[]
  pairs: MemoryPair[]
  /** The entries whose review fell due, the earliest due first. */
  review_queue: MemoryRecord[]
  /** The page of search results, of `matched` files that held every word (CF-1195). */
  results: Found[]
  matched: number
  page: number
  size: number
  /** The memory filing the board could not land (CF-922), or null. */
  filing: MemoryFiling | null
}

interface MemoryFiling {
  worktree: string
  outcome: string
  at: number
}

const keyOf = (r: { repository: string; id: string }): string => `${r.repository}/${r.id}`

/** The entries that wait for a review: those `queue` names as due, and those with no source; the
 * earliest due first. A proposal waits for approval instead. */
export function reviewDue(active: MemoryRecord[], queue: MemoryRecord[]): MemoryRecord[] {
  const due = new Set(queue.map(keyOf))
  return active
    .filter((r) => !r.proposed && (due.has(keyOf(r)) || r.source.trim() === ''))
    .sort((a, b) => a.review_due.localeCompare(b.review_due) || keyOf(a).localeCompare(keyOf(b)))
}

export type LoadGroup = 'core' | 'spec' | 'build' | 'review' | 'paths' | 'archive' | 'off'
const ROLES = ['spec', 'build', 'review'] as const

/** The words of a scope, as the server separates them. */
const terms = (scope: string): string[] =>
  scope
    .split(',')
    .map((t) => t.trim())
    .filter((t) => t !== '')

/** Whether a scope term is a path glob rather than a word. */
const isGlob = (term: string): boolean => /[/*?[.]/.test(term)

/** The group an entry is listed in: none it loads in, else every session, else the first role
 * its scope names, else the paths; the archive stands alone. */
function groupOf(r: MemoryRecord): LoadGroup {
  if (!r.loaded && !r.left_out) return 'off'
  const named = terms(r.scope)
  if (named.includes('archive')) return 'archive'
  if (!named.length || named.includes('core')) return 'core'
  return ROLES.find((role) => named.includes(role)) ?? 'paths'
}

/** The active entries by where they load, proposals left out: they wait in their queue. */
export function loadGroups(active: MemoryRecord[]): [LoadGroup, MemoryRecord[]][] {
  const listed = active.filter((r) => !r.proposed)
  return (['core', 'spec', 'build', 'review', 'paths', 'archive', 'off'] as const).map((g) => [
    g,
    listed.filter((r) => groupOf(r) === g),
  ])
}

/** Whether an entry loads in more than one place, or in sessions changing a path. */
export const loadsElsewhere = (r: MemoryRecord): boolean => {
  const named = terms(r.scope)
  return named.length > 1 || named.some(isGlob)
}

/** The characters `rows` add to a session. */
export const sizeOf = (rows: MemoryRecord[]): number => rows.reduce((sum, r) => sum + r.chars, 0)

/** The statement of the entry `id` of `repository`, active or retired, else the id itself. */
export function statementOf(
  repository: string,
  id: string,
  entries: { repository: string; id: string; statement: string }[],
): string {
  return entries.find((e) => e.repository === repository && e.id === id)?.statement ?? id
}
/** Whole days from a `YYYY-MM-DD` date to now, in UTC. */
export function daysSince(date: string, now: number = Date.now()): number {
  return Math.floor((now - Date.parse(`${date}T00:00:00Z`)) / 86_400_000)
}

export interface ArchivedRow {
  repository: string
  id: string
  title: string
  type: string
  stage: Stage
  archived: boolean
  archived_at: number
  /** The version whose release notes name a released ticket; empty for any other. */
  release: string
}

export interface Archive {
  rows: ArchivedRow[]
  archived_count: number
  sort: string
  dir: string
}

/** The archive read for one page: the rows the search matched, of which `rows` is page `page` of
 *  `size` (CF-1191). */
export interface PagedArchive extends Archive {
  total: number
  page: number
  size: number
}

const SORTS = ['id', 'title', 'type', 'stage', 'priority', 'assignee', 'repository', 'archived']

/** The archive's order from its address: the asked column and direction, else newest first. */
export function currentSort(sort: string, dir: string): [string, string] {
  return SORTS.includes(sort) ? [sort, dir] : ['archived', 'desc']
}

/** The kinds of archived ticket a person can ask for: both, or one alone (CF-1207). */
export const KINDS = [
  ['', 'All'],
  ['released', 'Released'],
  ['hand', 'By hand'],
] as const

/** The kind the address names: `released` or `hand`, else both. */
export function currentKind(show: string): string {
  return KINDS.some(([key]) => key && key === show) ? show : ''
}

/** The archive address sorted by a column: descending first, flipped when it is the current. It
 *  keeps the search, the kind shown and the page size and goes back to the first page (CF-1191). */
export function sortUrl(
  query: string,
  current: [string, string],
  column: string,
  size = '',
  show = '',
): string {
  const flip = current[0] === column && current[1] === 'desc' ? 'asc' : 'desc'
  const pairs: [string, string][] = query ? [['q', query]] : []
  const kind: [string, string][] = show ? [['show', show]] : []
  const sized: [string, string][] = size ? [['size', size]] : []
  return `/archive?${new URLSearchParams([...pairs, ['sort', column], ['dir', flip], ...kind, ...sized]).toString()}`
}

/** The archive address showing a kind: the search, the sort and the page size kept, the page left
 *  out. */
export function kindUrl(address: Record<string, string>, show: string): string {
  const pairs = [
    ['q', address.q],
    ['sort', address.sort],
    ['dir', address.dir],
    ['show', show],
    ['size', address.size],
  ].filter((pair): pair is [string, string] => Boolean(pair[1]))
  return pairs.length ? `/archive?${new URLSearchParams(pairs).toString()}` : '/archive'
}

/** A moment's UTC date, as `YYYY-MM-DD`. */
export function dateOf(at: number): string {
  return new Date(at * 1000).toISOString().slice(0, 10)
}
