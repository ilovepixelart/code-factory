// The Team page's read, `GET /api/team/now`, and the
// words the page draws from it that are only formatting (CF-1162).

import { hourMinute, span } from './format'
import {
  BotIcon,
  ComputerTerminal01Icon,
  KanbanIcon,
  Tick02Icon,
  UserGroupIcon,
  UserIcon,
} from '@hugeicons/core-free-icons'
import type { Icon } from './icon'

export type Group = 'needs_you' | 'waiting' | 'working' | 'done_today' | 'stale'
type RowState = 'owner' | 'stale' | 'waiting' | 'working' | 'merged'
export type ActorKind = 'agent' | 'session' | 'reviewer' | 'board' | 'gate' | 'owner'
export type Stage = 'first_commit' | 'pull_request' | 'gate_pass' | 'merged'

export interface TeamRow {
  key: string
  state: RowState
  ticket: { repository: string; id: string; title: string } | null
  actor: { kind: ActorKind; name: string }
  line: string
  since: number
  until: number | null
  /** The ticket's other states, most urgent first: one row per ticket (CF-1209). */
  also: Also[]
  pull: {
    number: number
    url: string
    gate: 'passed' | 'failed' | 'running' | 'not_run'
    merge: 'open' | 'conflict' | 'merged'
  } | null
}

export type Also = Pick<TeamRow, 'state' | 'actor' | 'line' | 'since' | 'until'>

interface Median {
  median: number | null
  count: number
}

export interface StageTimes {
  stage: Stage
  today: Median
  cycle: Median
}

export interface Peek {
  type: string
  column: string
  milestones: { stage: 'filed' | Stage; at: number | null; cycle: number | null }[]
  events: { at: number; words: string }[]
}

export interface TeamNow {
  now: number
  today: number
  cycle: { since: number; from: string }
  counts: Record<Group, number>
  groups: Record<Group, TeamRow[]>
  idle: string[]
  paused: string[]
  stages: StageTimes[]
  peek: Record<string, Peek>
}

/** The groups in the order the page shows them, with their titles, hints and empty lines, and
 *  the prefix of each one's page in the address. */
export const GROUPS: {
  group: Group
  title: string
  hint: string
  empty: string
  /** What puts work in the group or where to find it. */
  next: string
  /** A check where an empty group means nothing is wrong, the page's own icon where it is only empty. */
  icon: Icon
  prefix: string
  /** It is answered in the Inbox, so it links there. */
  inbox?: boolean
}[] = [
  {
    group: 'needs_you',
    title: 'Waiting on you',
    hint: 'oldest first',
    empty: 'Nothing waits on you',
    next: 'Open questions and screenshots that need your approval appear here.',
    icon: Tick02Icon,
    prefix: 'needs_',
    inbox: true,
  },
  {
    group: 'waiting',
    title: 'Waiting',
    hint: 'oldest first, each on what it waits for',
    empty: 'Nothing waits',
    next: 'Work waiting on review, checks, or a merge appears here.',
    icon: Tick02Icon,
    prefix: 'waiting_',
  },
  {
    group: 'working',
    title: 'Working',
    hint: 'longest first',
    empty: 'Nobody is working',
    next: 'Start an agent on a ticket and it works here.',
    icon: UserGroupIcon,
    prefix: 'working_',
  },
  {
    group: 'done_today',
    title: 'Done today',
    hint: 'age: from filing to merge',
    empty: 'Nothing merged today',
    next: 'See Recently merged in Flow for earlier merges.',
    icon: UserGroupIcon,
    prefix: 'done_',
  },
  {
    group: 'stale',
    title: 'Stale',
    hint: 'oldest first, quiet for 10 minutes or its process gone',
    empty: 'Nothing is stale',
    next: 'Work that stops reporting progress appears here.',
    icon: Tick02Icon,
    prefix: 'stale_',
  },
]

/** The rows of a group's page. */
export const GROUP_SIZE = 10

/** The strip's label of each stage, measured from filing. */
export const STAGE_LABELS: Record<Stage, string> = {
  first_commit: 'Filed to first commit',
  pull_request: 'to pull request',
  gate_pass: 'to checks pass',
  merged: 'to merge',
}

/** The peek's label of each milestone. */
export const MILESTONE_LABELS: Record<'filed' | Stage, string> = {
  filed: 'Filed',
  first_commit: 'First commit',
  pull_request: 'Pull request',
  gate_pass: 'Checks pass',
  merged: 'Merged',
}

/** Each actor's icon. */
export const ACTOR_ICONS: Record<ActorKind, Icon> = {
  agent: BotIcon,
  session: BotIcon,
  reviewer: BotIcon,
  board: KanbanIcon,
  gate: ComputerTerminal01Icon,
  owner: UserIcon,
}

/** Each actor's role, the label of its icon. */
export const ACTOR_ROLES: Record<ActorKind, string> = {
  agent: 'Agent',
  session: 'Claude session',
  reviewer: 'Review agent',
  board: 'The board',
  gate: 'The checks',
  owner: 'You',
}

/** A row's age: from its start to its finish, or to now while it lasts. */
export function age(row: Pick<TeamRow, 'since' | 'until'>, now: number): string {
  return span((row.until ?? now) - row.since)
}

/** What a row says it does: a done row says when it merged. */
export function rowLine(row: Pick<TeamRow, 'state' | 'line' | 'until'>): string {
  if (row.state !== 'merged' || row.until === null) return row.line
  return [`merged at ${hourMinute(row.until)}`, row.line].filter(Boolean).join(', ')
}

const ALSO_WORDS: Record<RowState, string> = {
  owner: 'waiting on you',
  stale: 'stale',
  waiting: 'waiting',
  working: 'working',
  merged: 'merged',
}

/** A row's second line: `also stale 50d: agent failed`, `also working 9m: builder, build run`. */
export function alsoLine(also: Also, now: number): string {
  const who = also.actor.kind === 'owner' || also.state === 'merged' ? '' : also.actor.name
  const what = [who, rowLine(also)].filter(Boolean).join(', ')
  return `also ${ALSO_WORDS[also.state]} ${age(also, now)}${what ? `: ${what}` : ''}`
}

/** Whether no ticket reached any stage today or this cycle: the strip has nothing to show. */
export function noStageTimes(stages: StageTimes[]): boolean {
  return stages.every((stage) => stage.today.count === 0 && stage.cycle.count === 0)
}

/** How today's median stands against the cycle's, in words: `8m over`, `3m under`. */
export function against(today: number | null, cycle: number | null): string {
  if (today === null || cycle === null) return ''
  const gap = today - cycle
  if (Math.abs(gap) < 1) return 'on the cycle median'
  return `${span(Math.abs(gap))} ${gap > 0 ? 'over' : 'under'}`
}

/** A strip cell's bar: today's length and the cycle's mark, as percents of one scale. */
export function bar(today: number | null, cycle: number | null): { fill: number; mark: number } {
  const scale = Math.max(today ?? 0, cycle ?? 0) * 1.25
  if (scale <= 0) return { fill: 0, mark: 0 }
  return { fill: ((today ?? 0) / scale) * 100, mark: ((cycle ?? 0) / scale) * 100 }
}

/** A pull request's state in words, merge state first: `merged`, `conflict`, `checks passed`. */
export function pullWords(pull: NonNullable<TeamRow['pull']>): string {
  if (pull.merge !== 'open') return pull.merge
  return `checks ${pull.gate.replace('_', ' ')}`
}

/** A pull request's dot in the theme's tokens: primary when it holds, destructive when it fails,
 *  muted while its checks run, and fainter still before they do. */
export function pullDot(pull: NonNullable<TeamRow['pull']>): string {
  if (pull.merge === 'merged' || (pull.merge === 'open' && pull.gate === 'passed'))
    return 'bg-primary'
  if (pull.merge === 'conflict' || pull.gate === 'failed') return 'bg-destructive'
  if (pull.gate === 'running') return 'bg-muted-foreground'
  return 'bg-muted-foreground/30'
}

/** The peek of a row's ticket, by `<repository>/<id>`. */
export function peekKey(row: TeamRow): string {
  return row.ticket ? `${row.ticket.repository}/${row.ticket.id}` : ''
}
