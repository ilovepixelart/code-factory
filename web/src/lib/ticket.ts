// A ticket's page content as `GET /api/tickets/{repository}/{id}` answers it, and the fields the panel and page edit.

import type { AtWork } from '../generated/AtWork'
import { request } from './actions'
import type { Card, Stage } from './board'

/** The tab label of each document a ticket page shows. */
export const DOCUMENT_LABELS: Record<string, string> = {
  requirements: 'Requirements',
  mock: 'Mock',
  spec: 'Spec',
  uat: 'UAT',
}
import { readJson } from './actions'
import type { Asked } from './questions'

interface Evidence {
  stage: Stage
  required: boolean
  present: boolean
  detail: string
}

/** A recorded run: whether it held, and its commit and tree. */
interface SummaryRun {
  held: boolean
  commit: string
  tree: string
}

/** What a ticket proved and what it did not (CF-400). */
export interface Summary {
  gate: SummaryRun | null
  verdict: string
  capture: { tree: string; approved: boolean } | null
  not_proven: string[]
}

/** What an active run has done so far, from its own log; null where it cannot tell (CF-1036). */
export interface RunProgress {
  tool_calls: number | null
  reads: number | null
  changes: number | null
  files: { count: number; names: string[] } | null
  tokens: number | null
  last_activity: number | null
}

export interface TicketView {
  ticket: Record<string, string | boolean | number>
  repository: string
  checklist: Evidence[]
  summary: Summary
  current_stage: Stage
  work_done: boolean
  runs: {
    id: string
    stage: Stage
    iteration: number
    loop: boolean
    started_at: number
    progress: RunProgress
    /** The memory entries the run received and recall left out, by id; null when none (CF-1169). */
    memory: RunMemory | null
    /** When the owner's context it received became current, in epoch seconds (CF-1163). */
    context_at: number | null
  }[]
  /** Where the ticket stands, as the server reads it (CF-1199); absent from the view a ticket's
   * files alone make. */
  card?: Card | null
  /** Seconds in each column by its recorded moves; null for one never entered. */
  columns?: { spec: number | null; build: number | null; review: number | null }
  status?: TicketStatus
  /** The branch it is worked on: its own `branch:`, else its worktree's; empty for none (CF-1229).
   * The server adds it, absent from the view a ticket's files alone make. */
  branch?: string
  /** The session subagents at work on it, as its card lists them (CF-1184); the server adds
   * them, absent from the view a ticket's files alone make. */
  subagents?: AtWork[]
  spent: number
  /** A cost of `spent` is the board's estimate; absent when none is (CF-1216). */
  spent_estimated?: boolean
  /** What the ticket's runs cost, in parts; each null when no run reported it (CF-651). */
  cost: {
    total: number | null
    review: number | null
    cache_read: number | null
    turns: number | null
  }
  budget: number | null
  default_budget: number | null
  halted: string
  /** The repository's spend this UTC month against `[agents] monthly_budget_usd`, and the day
   * it is spent at the month's pace so far; null without that budget (CF-671). */
  month_budget: {
    month: string
    spent: number
    budget: number
    runs_out: string | null
    reached: boolean
  } | null
  questions: (Asked & { answer: string; answered_by: string })[]
  /** In writing order; the mock, for a ticket labelled ui, also names the files under mock/. */
  documents: { stage: string; html: string | null; files?: string[] }[]
  /** The checklist of plan.md on the ticket's branch, null without one (CF-1219). */
  plan: { items: { text: string; done: boolean }[]; done: number; total: number } | null
  link: {
    open_blockers: string[]
    blocks: string[]
    parent: string
    children: number
    children_done: number
    child_ids: string[]
  } | null
  titles: Record<string, string>
  stages_by_id: Record<string, Stage>
  /** Each linked ticket the board holds, whatever its repository. */
  linked: Record<string, { repository: string; title: string; stage: Stage }>
  description_html: string
  check: {
    at: string
    commit: string
    exit_code: number
    log: string
    tree: string
    reason?: string
  } | null
  check_log: string
  /** What the latest run, when a runner on another machine reported it, sent of its log. */
  runner_log?: string
  checks_configured: boolean
  /** Whether the board runs the checks for the ticket now. */
  checking: boolean
  activity: ActivityEntry[]
}

/** The columns an agent can be started in. */
export const AGENT_STAGES: Stage[] = ['spec', 'build']

/** The fields the form edits, in its order. */
export const FIELDS = [
  'title',
  'description',
  'stage',
  'type',
  'priority',
  'due',
  'labels',
  'assignee',
  'blocked',
  'blocked_by',
  'parent',
  'branch',
  'e2e',
  'tests',
  'pages',
  'caused_by',
  'budget',
  'parallel',
] as const
export type Field = (typeof FIELDS)[number]

/**
 * What a save sends: every editable field, as text; given the values as last saved, only the
 * fields that differ from them, so a save does not write back a change made elsewhere.
 */
export function fieldsOf(
  ticket: Record<string, string | number | boolean | null | undefined>,
  since?: Partial<Record<Field, string>>,
): Record<Field, string> {
  const text = (f: Field): string => String(ticket[f] ?? '')
  const fields = since ? FIELDS.filter((f) => f in ticket && text(f) !== (since[f] ?? '')) : FIELDS
  return Object.fromEntries(fields.map((f) => [f, text(f)])) as Record<Field, string>
}

/** The footer's words for a save the board or the form refused. */
export const NOT_SAVED = 'Not saved'

/** Take a blank title out of a save's fields, and say whether there was one: a ticket without a
 *  title cannot be read back, so the board refuses it and the form never sends it. */
export function dropBlankTitle(changed: Partial<Record<Field, string>>): boolean {
  const blank = changed.title?.trim() === ''
  if (blank) delete changed.title
  return blank
}

/** The page content of a ticket, or null when there is no such ticket; any other failure throws,
 *  so a read the board did not answer is not taken for a deleted ticket. */
export async function loadTicket(repository: string, id: string): Promise<TicketView | null> {
  const path = `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}`
  const response = await request(path)
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path} answered ${String(response.status)}`)
  return (await response.json()) as TicketView
}

/** One line of a branch's change: its number in the new file, none for a removed line. */
export interface DiffLine {
  kind: 'added' | 'removed' | 'kept'
  number: number | null
  text: string
}

/** A ticket branch's changes against its merge base (`GET .../diff`). */
export interface TicketChanges {
  files: { path: string; lines: DiffLine[] }[]
  cut: boolean
  limit: number
  branch: string
  default_branch: string
}

/** The changes of a ticket's branch, or null when there is no such ticket. */
export async function loadChanges(repository: string, id: string): Promise<TicketChanges | null> {
  return readJson<TicketChanges>(
    `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}/diff`,
  )
}

/** The address of a ticket's page in the app. */
export function ticketHref(repository: string, id: string): string {
  return `/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}`
}

/** One entry of a ticket's activity; a `run` entry (CF-1075) also holds its run's fields. */
/** The memory entries a run received and recall left out, by id (CF-1169). */
export interface RunMemory {
  digest: string
  received: string[]
  left_out: string[]
}

/** A merge conflict standing on the branch tip, and the latest capture (CF-1199). */
interface TicketStatus {
  /** `with` and `files` while a conflict stands on `tip`; null without a branch. */
  conflict: { tip: string; with?: string; files?: string } | null
  capture: {
    tree: string
    images: string[]
    state: 'waits' | 'approved' | 'sent_back'
    by?: string
    reason?: string
  } | null
}

export interface ActivityEntry {
  at: number
  sentence: string
  kind: string
  text: string
  run?: string
  agent?: string
  model?: string
  stage?: string
  iteration?: number
  outcome?: string
  exit_code?: number | null
  duration?: number | null
  tokens?: number | null
  memory?: RunMemory
  context_at?: number
  /** A coordinator's edit (CF-1428): the field and the values it replaced. */
  edit?: { name: string; from: string; to: string }
}
