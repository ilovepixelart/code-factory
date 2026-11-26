// What the Agents page reads and sends.

import type { AgentDefinition } from '../generated/AgentDefinition'
import type { Doing } from '../generated/Doing'
import type { Last as LastRun } from '../generated/Last'
import type { ModelCheck } from '../generated/ModelCheck'
import { STAGE_LABELS, type Stage } from './board'
import { thousands } from './format'

export type { Doing }
/** An agent's latest run, its column one of the board's stages. */
export type Last = Omit<LastRun, 'stage'> & { stage: Stage }

/** A guarantee of the board's that a runtime does not hold, and why. */
export interface Gap {
  guarantee: string
  why: string
}

export interface AgentList {
  agents: AgentDefinition[]
  runtimes: string[]
  roles: Stage[]
  /** Each runtime's gaps, by its name; empty for a runtime holding every guarantee. */
  gaps: Record<string, Gap[]>
  doing: Record<string, Doing>
  /** Each agent's latest run, for the agents that have one. */
  last: Record<string, Last>
  /** Each agent's last model check, while its runtime, connection and model are those it was taken with. */
  checks: Record<string, ModelCheck>
  /** Whether any tracked repository starts agents on its own. */
  starting: boolean
  problem: string
}

/** An agent as its form holds it: the limits as typed, empty for none, run time in minutes. */
export interface AgentDraft {
  name: string
  runtime: string
  connection: string
  model: string
  roles: string[]
  /** The ticket types it takes; empty: every type (CF-1273). */
  types: string[]
  /** The labels it takes, comma separated as typed; empty: any labels. */
  labels: string
  tokens: number | ''
  minutes: number | ''
  context: string
}

/** The form's start for an agent, or for a new one on the first runtime. */
export function draftOf(agent: AgentDefinition | null, runtime = 'claude'): AgentDraft {
  if (!agent)
    return {
      name: '',
      runtime,
      connection: '',
      model: '',
      roles: [],
      types: [],
      labels: '',
      tokens: '',
      minutes: '',
      context: '',
    }
  return {
    name: agent.name,
    runtime: agent.runtime,
    connection: agent.connection,
    model: agent.model,
    roles: [...agent.roles],
    types: [...(agent.types ?? [])],
    labels: (agent.labels ?? []).join(', '),
    tokens: agent.max_tokens ?? '',
    minutes: agent.max_seconds === null ? '' : agent.max_seconds / 60,
    context: agent.context ?? '',
  }
}

/** What an add or a change sends for a draft: an empty limit is none. */
export function bodyOf(draft: AgentDraft): object {
  return {
    name: draft.name.trim(),
    runtime: draft.runtime,
    connection: draft.connection,
    model: draft.model.trim(),
    roles: draft.roles,
    types: draft.types,
    labels: draft.labels
      .split(',')
      .map((label) => label.trim())
      .filter((label) => label !== ''),
    max_tokens: draft.tokens === '' ? null : draft.tokens,
    max_seconds: draft.minutes === '' ? null : Math.round(draft.minutes * 60),
    context: draft.context,
  }
}

/** A text's length as the board counts a context: in characters, not UTF-16 units. */
export const characters = (text: string): number => Array.from(text).length

/** The Context field's count (CF-1163): its words, in the warning tone past 90% of the limit and
 * the error tone past the limit, with how far over. */
export function contextCount(text: string, limit: number): { text: string; tone: string } {
  const length = characters(text)
  const said = `${thousands(length)} of ${thousands(limit)} characters`
  if (length > limit)
    return { text: `${said}, ${thousands(length - limit)} over`, tone: 'text-destructive' }
  return { text: said, tone: length * 10 > limit * 9 ? 'text-foreground' : 'text-muted-foreground' }
}

/** The run named on an agent's card with the context version it received. */
export interface ContextRun {
  run: string
  ticket: string
  at: string
}

/** What an agent's card says of its context (CF-1163): its size, whether its next run receives
 * the current version, and the last run that received one, with that version's time by `when`. */
export function contextLine(
  agent: AgentDefinition,
  last: Last | undefined,
  when: (seconds: number) => string,
): { size: string; next: boolean; received: ContextRun | null } | null {
  if (agent.context === undefined) return null
  const size = `Context: ${thousands(characters(agent.context))} characters`
  const received =
    last?.context_at === undefined
      ? null
      : {
          run: last.run,
          ticket: `${last.id} ${STAGE_LABELS[last.stage]}`,
          at: when(last.context_at),
        }
  return { size, next: last?.context_at !== agent.context_at, received }
}

/** A time limit in whole minutes, else in seconds, never rounded away (CF-480). */
const timeLimit = (seconds: number): string =>
  seconds % 60 === 0 ? `${String(seconds / 60)} min` : `${String(seconds)} s`

/** An agent's limits in words, or that it has none. */
export function limitsText(agent: AgentDefinition): string {
  const parts = [
    agent.max_tokens === null ? '' : `${agent.max_tokens.toLocaleString('en')} tokens`,
    agent.max_seconds === null ? '' : timeLimit(agent.max_seconds),
  ].filter((part) => part !== '')
  return parts.length ? parts.join(' · ') : 'no token or time limit'
}

/** What an agent's card says of the tickets it takes, or null when it takes every one (CF-1273). */
export function takesText(agent: AgentDefinition): string | null {
  const types = agent.types ?? []
  const labels = agent.labels ?? []
  const parts = [
    types.length ? `types ${types.join(', ')}` : '',
    labels.length ? `labels ${labels.join(', ')}` : '',
  ].filter((part) => part !== '')
  return parts.length ? `Takes only ${parts.join(' · ')}` : null
}

type Tone = 'default' | 'warning' | 'error'

/** One limit's meter: what is used of it, in words, and its tone. */
export interface Meter {
  limit: 'tokens' | 'time'
  used: number
  max: number
  text: string
  tone: Tone
}

/** The longest name the board takes (`NAME_LIMIT`). */
export const NAME_LIMIT = 40

const TONES: Tone[] = ['default', 'warning', 'error']

/** The warning tone from 75% of the limit, the error tone from 100%. */
function toneOf(used: number, max: number): Tone {
  if (used >= max) return 'error'
  return used * 4 >= max * 3 ? 'warning' : 'default'
}

/** Tokens in millions or thousands with one decimal at most, rounded down: "1.2 M", "150 k". */
function tokensText(tokens: number): string {
  for (const [size, unit] of [
    [1_000_000, 'M'],
    [1_000, 'k'],
  ] as const) {
    if (tokens >= size) return `${String(Math.floor(tokens / (size / 10)) / 10)} ${unit}`
  }
  return String(tokens)
}

/** The meters of an agent holding a ticket, one per limit it has; tokens only once reported. */
export function metersOf(agent: AgentDefinition, doing: Doing | undefined): Meter[] {
  const usage = doing?.usage
  if (!usage) return []
  const meters: Meter[] = []
  if (agent.max_tokens !== null && usage.tokens !== null) {
    const [used, max] = [usage.tokens, agent.max_tokens]
    const text = `${tokensText(used)} of ${tokensText(max)} tokens`
    meters.push({ limit: 'tokens', used, max, text, tone: toneOf(used, max) })
  }
  if (agent.max_seconds !== null) {
    const [used, max] = [usage.seconds, agent.max_seconds]
    const text = `${String(Math.floor(used / 60))} of ${String(Math.round(max / 60))} min`
    meters.push({ limit: 'time', used, max, text, tone: toneOf(used, max) })
  }
  return meters
}

/** Whether an agent with a token limit holds a ticket whose tokens its runtime has not reported. */
export function tokensLater(agent: AgentDefinition, doing: Doing | undefined): boolean {
  return agent.max_tokens !== null && doing?.usage?.tokens === null
}

const ATTENTION = [
  'over limit',
  'check failed',
  'waiting',
  'usage limit',
  'unreachable',
  'working',
  'paused',
  'idle',
]

/**
 * An agent's status word: what it is doing, else why its runs are held (paused by the owner, its
 * kept model check failed, its last run parked its ticket on a usage limit; CF-473), else idle.
 */
export function agentState(
  agent: AgentDefinition,
  doing: Doing | undefined,
  last: Last | undefined,
  check: ModelCheck | undefined,
): string {
  if (doing) return doing.state
  if (agent.paused_at !== undefined) return 'paused'
  if (check && !check.passed) return 'check failed'
  return last?.outcome === 'usage limit' ? 'usage limit' : 'idle'
}

/** An agent's status word by its name ([`agentState`]). */
function stateOf(list: AgentList, name: string): string {
  const agent = list.agents.find((each) => each.name === name)
  if (!agent) return 'idle'
  return agentState(agent, list.doing[name], list.last[name], list.checks[name])
}

/**
 * The agents, the ones needing attention first, each state in the file's order; an agent that
 * cannot reach its model (`unreachable`) ranks after waiting unless its state ranks before.
 */
export function byAttention(
  list: AgentList,
  unreachable: (name: string) => boolean = () => false,
): AgentDefinition[] {
  const rank = (agent: AgentDefinition) => {
    const state = ATTENTION.indexOf(stateOf(list, agent.name))
    return unreachable(agent.name) ? Math.min(state, ATTENTION.indexOf('unreachable')) : state
  }
  return [...list.agents].sort((a, b) => rank(a) - rank(b))
}

const pauseSaid = (agent: AgentDefinition): string =>
  `${agent.name} ${agent.paused_at === undefined ? 'resumed' : 'paused'}`

function said(name: string, doing: Doing | undefined): string {
  if (!doing) return `${name} idle`
  if (doing.state === 'working') return `${name} started ${doing.id}`
  return doing.state === 'waiting' ? `${name} waiting` : `${name} over its limit`
}

/** The meters of `agent` that reached a higher tone on the same ticket, in words. */
function crossed(agent: AgentDefinition, was: Doing | undefined, now: Doing | undefined): string[] {
  if (!was || was.id !== now?.id) return []
  const before = metersOf(agent, was)
  return metersOf(agent, now)
    .filter((meter) => {
      const tone = before.find((m) => m.limit === meter.limit)?.tone ?? 'default'
      return TONES.indexOf(meter.tone) > TONES.indexOf(tone)
    })
    .map((meter) => {
      const limit = meter.limit === 'tokens' ? 'token' : 'time'
      return meter.tone === 'error'
        ? `${agent.name} at its ${limit} limit`
        : `${agent.name} at 75% of its ${meter.limit}`
    })
}

/** What changed between two reads, for agents in both: each change of status, and each meter
 * reaching 75% or its limit, in words. */
export function changesOf(before: AgentList, after: AgentList): string {
  const known = new Set(before.agents.map((agent) => agent.name))
  return after.agents
    .filter((agent) => known.has(agent.name))
    .flatMap((agent) => {
      const [was, now] = [before.doing[agent.name], after.doing[agent.name]]
      const moved = was?.state !== now?.state || was?.id !== now?.id
      const pausedBefore = before.agents.some(
        (a) => a.name === agent.name && a.paused_at !== undefined,
      )
      const pause = pausedBefore === (agent.paused_at !== undefined) ? [] : [pauseSaid(agent)]
      return [...(moved ? [said(agent.name, now)] : []), ...pause, ...crossed(agent, was, now)]
    })
    .join('; ')
}

/** Each column any agent works, with its agents in the order runs take them: agents.json's order,
 * which the route answers (CF-915). */
export function runOrder(list: AgentList): { column: Stage; agents: AgentDefinition[] }[] {
  return list.roles
    .map((column) => ({ column, agents: list.agents.filter((a) => a.roles.includes(column)) }))
    .filter((entry) => entry.agents.length > 0)
}
