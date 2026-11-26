// What the Flow page and the Inbox read.

import type { RangeKey } from './analytics'
import type { Stage } from './board'
import type { MemoryKind } from './memory'
import type { Asked } from './questions'

/** One pull request merged into a tracked repository's default branch (CF-1203). */
export interface Merged {
  repository: string
  pull: number | null
  /** The pull request on GitHub, when `origin` is there. */
  url: string | null
  branch: string
  ticket: string | null
  title: string
  /** When it merged, epoch seconds. */
  at: number
  /** Seconds to the merge from `from`: the ticket's filing, else the branch's first commit. */
  lead: number
  from: 'filed' | 'first_commit'
  /** Whether a later commit from outside its own change reverted it (CF-1215). */
  reverted: boolean
  /** The tickets whose `caused_by` names its ticket. */
  fixes: string[]
  /** What the board's last checks record on the commit it merged said; `none` without one. */
  checks: 'passed' | 'failed' | 'none'
  /** What the ticket's runs cost; absent when none recorded a cost (CF-1300). */
  cost?: number
  /** A cost among those summed is the board's estimate. */
  cost_estimated?: boolean
  /** Whether a run of the ticket made every commit it merged (CF-1302). */
  autonomy: 'autonomous' | 'assisted' | 'unknown'
}

/** A ticket on a branch, with how long its work has been going. */
interface InFlight {
  repository: string
  id: string
  title: string
  stage: Stage
  /** Seconds since its branch was cut; null when git cannot tell. */
  age: number | null
  needs: string
}

/** The board's runs of one agent on one model and connection in the window (CF-1214). */
interface AgentRuns {
  agent: string
  /** Empty for the harness's default model. */
  model: string
  /** Empty for a run on no connection, or one whose connection the board cannot tell. */
  connection: string
  runs: number
  finished: number
  failed: number
  stopped: number
  running: number
  /** How the runs that did not finish ended, the most frequent first. */
  endings: { reason: string; count: number }[]
  tokens: number | null
  cost: number | null
  /** A cost of the sum is the board's estimate; absent when none is (CF-1216). */
  estimated?: boolean
}

/** `GET /api/flow`: what shipped in the window, how long it took, what is stuck, and the runs. */
export interface Flow {
  range: RangeKey
  since: number
  now: number
  merged: Merged[]
  lead: { median: number | null; p85: number | null; p95?: number | null; count: number }
  completion?: { started: number; merged: number }
  /** The median cost of the merged tickets that have one: `count` of the `of` merged tickets (CF-1300). */
  cost: { median: number | null; estimated: boolean; count: number; of: number }
  /** The merged tickets by whether a hand commit went into them; `share` is null while none is classed (CF-1302). */
  autonomy: { share: number | null; autonomous: number; assisted: number; unknown: number }
  /** The median minutes the merged tickets spent in each column; null when none entered it. */
  columns: { spec: number | null; build: number | null; review: number | null }
  in_flight: number
  stuck_after: number
  stuck: InFlight[]
  agents: AgentRuns[]
}

export interface InboxItem {
  since: number | null
  kind: string
  reason: string
  note: string
  count: number
  images: string[]
  ticket: { repository: string; id: string; title: string } | null
  question: Asked | null
  session: {
    session_id: string
    cwd: string
    action: { tool: string; summary: string } | null
  } | null
  request: { id: string; tool: string; summary: string } | null
  /** The proposed memory entry a `memory` item asks about (CF-1168); null on every other item. */
  memory?: MemoryProposalItem | null
  /** The failing run a `main` item shows (CF-1251); null on every other item. */
  main?: MainRun | null
  /** The coordinator's diagnosis a `diagnoses` item shows (CF-1428); null on every other item. */
  diagnosis?: { author: string; text: string } | null
  /** A merge item's pull request size, when GitHub counted it; null on every other item. */
  size?: { additions: number; deletions: number; changed_files: number } | null
}

/** A default branch's own run that failed. */
interface MainRun {
  repository: string
  commit: string
  /** The gate step that failed, `setup` for the worktree setup; empty when the log names none. */
  step: string
  exit_code: number
  reason?: string
  log: string
  /** The log's last lines. */
  tail: string
  /** The last commit the run passed on; empty when it never passed. */
  passed: string
  /** The merge the search found failing first, and the ticket it brought; empty when none. */
  broken_by: string
  ticket: string
}

/** An agent's memory entry that waits for the owner's approval. */
interface MemoryProposalItem {
  repository: string
  id: string
  kind: MemoryKind
  statement: string
  why: string
  source: string
  guard: string
}

export const SECTIONS = [
  'main',
  'questions',
  'permissions',
  'rules',
  'memory',
  'sessions',
  'stopped',
  'screens',
  'mergeable',
  'failing',
  'idle',
  'reviews',
  'diagnoses',
] as const

export type Section = (typeof SECTIONS)[number]

/** Where new Inbox items are pushed (`code-factory push`), and the last delivery that failed. */
interface PushState {
  /** Empty when the target does not read. */
  host: string
  failure: { at: number; problem: string } | null
}

export type Inbox = Record<Exclude<Section, 'idle'>, InboxItem[]> & {
  idle?: InboxItem[]
  count: number
  latest: string
  next_up: { section: Section; index: number } | null
  push: PushState | null
}
