// What the Factory pages read (`GET /api/factory/*`, specification section 4.6): the answers'
// shapes, the range an address names and the words and points the pages draw from them. Instants
// are epoch seconds, durations seconds, costs USD or null.

import { RANGE_DAYS, type RangeKey } from './analytics'
export type Size = 'S' | 'M' | 'L' | 'XL'

interface Counted {
  key: string
  runs: number
}

export interface Runs {
  total: number
  by_stage: Counted[]
  by_state: Counted[]
  by_source: Counted[]
  by_model: Counted[]
  by_agent: Counted[]
}

interface Prs {
  opened: number
  merged: number
  merged_in_period: number
  open: number
  closed: number
}

interface SeriesPoint {
  start: number
  opened: number
  merged: number
}

export interface Series {
  bucket: 'day' | 'week'
  points: SeriesPoint[]
}

interface Timed {
  median: number | null
  count: number
}

interface CycleStage extends Timed {
  stage: 'kickoff_to_pr' | 'pr_to_review' | 'review_to_merge'
}

interface Cycle {
  total: Timed
  stages: CycleStage[]
}

interface Component {
  component: 'spec' | 'build' | 'review' | 'other'
  median: number | null
  total: number
}

interface SizeCost {
  size: Size
  median: number | null
  priced: number
  of: number
}

export interface Cost {
  median: number | null
  priced: number
  of: number
  estimated: boolean
  /** Judges and evals: not in any pull request's cost. */
  measurement: number
  by_component: Component[]
  by_size: SizeCost[]
}

export interface MergedCost {
  median: number | null
  priced: number
  owner_recorded: number
  merged: number
  estimated: boolean
}

export interface Expensive {
  url: string
  repository: string
  number: number
  ticket: string | null
  title: string
  state: string
  opened_at: number
  cost: number
  /** False when a run of the pull request's ticket has no recorded cost. */
  cost_complete: boolean
  estimated: boolean
  changed_lines: number | null
  size: Size | 'unknown'
  /** The ticket's runs in scope, shared with a sibling pull request. */
  runs: number
}

export interface ScorerCard {
  repository: string
  name: string
  question: string
  yes: number
  no: number
  unclear: number
  asked: number
  pass_rate: number | null
  average_score: number | null
  window: { from: number; to: number }
}

export interface ScorerCards {
  available: boolean
  cards: ScorerCard[]
}

export interface ImprovementItem {
  url: string
  number: number
  title: string
  state: string
  opened_at: number
  failures: number
}

export interface Improvements {
  available: boolean
  items: ImprovementItem[]
}

export interface Dashboard {
  from: number
  to: number
  now: number
  runs: Runs
  prs: Prs
  series: Series
  autonomy: { share: number | null; autonomous: number; assisted: number; unknown: number }
  cycle: Cycle
  cost: Cost
  merged_cost?: MergedCost
  expensive: Expensive[]
  scorers: ScorerCards
  improvements: Improvements
  fix_rounds?: FixRoundOutcome[]
  role_notes?: RoleNoteOutcome[]
}

export interface FixRoundOutcome {
  rounds: number
  merged: number
  closed: number
  open: number
  merge_rate: number | null
}

export interface RoleNoteOutcome {
  role: string
  notes: number
  fixed: number
}

export { RANGES, rangeOf, type RangeKey } from './analytics'

const DAY = 86_400_000

/** The UTC dates a read sends: tomorrow's midnight, so today is inside, and `range` before it. */
export function bounds(range: RangeKey, now: Date): { from: string; to: string } {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  const days = RANGE_DAYS[range]
  const date = (ms: number): string => new Date(ms).toISOString().slice(0, 10)
  return { from: date(today + DAY - days * DAY), to: date(today + DAY) }
}

/** A part of a total as a whole percent, or a dash while there is no total. */
export function share(part: number, total: number): string {
  return total === 0 ? '-' : `${String(Math.round((100 * part) / total))}%`
}

/** A number of pull requests, with the word that qualifies them: `1 PR`, `3 merged PRs`. */
export const prs = (n: number, kind = ''): string => {
  const qualifier = kind ? `${kind} ` : ''
  return `${String(n)} ${qualifier}${n === 1 ? 'PR' : 'PRs'}`
}

const SIZE_WORDS: Record<Size, string> = {
  S: 'S, under 100 lines',
  M: 'M, 100 to 499 lines',
  L: 'L, 500 to 999 lines',
  XL: 'XL, 1000 lines and up',
}

/** A size with its thresholds, or `unknown` while the changed lines were not recorded. */
export function sizeLabel(size: Size | 'unknown' | null): string {
  return size === null || size === 'unknown' ? 'unknown' : SIZE_WORDS[size]
}

/** How long a scorer's answers reach back: `last 7 days`. */
export function windowWords(window: { from: number; to: number }): string {
  const days = Math.round((window.to - window.from) / 86_400)
  return days === 1 ? 'last day' : `last ${String(days)} days`
}

export interface ChartPoint extends SeriesPoint {
  label: string
  /** The label under its bars, short enough for every bucket of the range to carry one. */
  tick: string
}

const WEEK = 7

/** The series' buckets labelled in UTC, the zone the answer counts in: a day and month (`week of` before it for a weekly bucket), ticked by it or, past a week of buckets, by the day of the month. */
export function chartPoints(series: Series): ChartPoint[] {
  return series.points.map((point) => {
    const at = new Date(point.start * 1000)
    const date = at.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
    return {
      ...point,
      label: series.bucket === 'week' ? `week of ${date}` : date,
      tick: series.points.length <= WEEK ? date : String(at.getUTCDate()),
    }
  })
}
