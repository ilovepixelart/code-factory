// A turn's entries as a trace (CF-1384): a bar per tool call on the turn's own time axis, a marker
// for each idle gap, and a subagent's calls nested under one row naming it.

import {
  BotIcon,
  ComputerTerminal01Icon,
  File01Icon,
  Link01Icon,
  PencilEdit01Icon,
  Search01Icon,
  Wrench01Icon,
} from '@hugeicons/core-free-icons'
import type { Icon } from './icon'
import { entryStatus } from './session_view'
import type { Entry, Session, Turn } from './sessions'
import { isFailed } from './sessions'

/** An idle gap shows a marker only when longer than this (seconds). */
const GAP_SECONDS = 60
/** The least a bar's width may be (percent of the axis), so an instant call still shows. */
const MIN_WIDTH = 0.5

/** A bar's place on the turn's axis, in percent. */
interface Bar {
  left: number
  width: number
}

interface EntryRow {
  type: 'entry'
  key: string
  entry: Entry
  /** The status word shown; an open call of a subagent that stopped reads `interrupted`. */
  status: string
  failed: boolean
  icon: IconKind
  /** Only a tool call has a bar; a prompt or a stop is a point in time. */
  bar: Bar | null
}

interface GapRow {
  type: 'gap'
  key: string
  seconds: number
}

interface AgentRow {
  type: 'agent'
  key: string
  name: string
  id: string
  calls: number
  failed: number
  /** The sum of its calls' own durations (seconds). */
  total: number
  bar: Bar
  rows: Row[]
}

export type Row = EntryRow | GapRow | AgentRow

type IconKind = Icon

const KINDS: Record<string, IconKind> = {
  Read: File01Icon,
  Edit: PencilEdit01Icon,
  MultiEdit: PencilEdit01Icon,
  Write: PencilEdit01Icon,
  NotebookEdit: PencilEdit01Icon,
  Bash: ComputerTerminal01Icon,
  Grep: Search01Icon,
  Glob: Search01Icon,
  Task: BotIcon,
  Agent: BotIcon,
  WebFetch: Link01Icon,
  WebSearch: Link01Icon,
}

/** The icon of a tool kind: read, edit, shell, search, subagent, web; any other tool a wrench. */
function toolIcon(tool: string): IconKind {
  return KINDS[tool] ?? Wrench01Icon
}

function endOf(entry: Entry): number {
  return entry.at + (entry.duration_seconds ?? 0)
}

interface Item {
  start: number
  end: number
  row: Row
}

function axisOf(turn: Turn): { start: number; length: number } {
  const start = turn.started_at
  const end = Math.max(start + (turn.duration_seconds ?? 0), ...turn.entries.map(endOf))
  return { start, length: end - start }
}

function barOf(axis: { start: number; length: number }, from: number, to: number): Bar {
  const length = axis.length || 1
  const width = Math.min(100, Math.max(MIN_WIDTH, ((to - from) * 100) / length))
  const left = Math.min(100 - width, Math.max(0, ((from - axis.start) * 100) / length))
  return { left: round(left), width: round(width) }
}

function round(percent: number): number {
  return Math.round(percent * 100) / 100
}

/** The items in order with an idle-gap row before each one that starts more than GAP_SECONDS
 * after everything before it ended. */
function withGaps(items: Item[]): Row[] {
  const rows: Row[] = []
  let ended = Number.NEGATIVE_INFINITY
  for (const item of items) {
    const idle = item.start - ended
    if (rows.length && idle > GAP_SECONDS) {
      rows.push({ type: 'gap', key: `gap-${item.row.key}`, seconds: idle })
    }
    rows.push(item.row)
    ended = Math.max(ended, item.end)
  }
  return rows
}

function entryItem(e: Entry, session: Session, axis: { start: number; length: number }): Item {
  const status = entryStatus(e, session)
  const tool = e.kind === 'tool'
  return {
    start: e.at,
    end: endOf(e),
    row: {
      type: 'entry',
      key: `e-${String(e.seq)}`,
      entry: e,
      status,
      failed: tool && isFailed(e.status),
      icon: toolIcon(e.title),
      bar: tool ? barOf(axis, e.at, endOf(e)) : null,
    },
  }
}

function agentItem(
  id: string,
  members: Entry[],
  session: Session,
  axis: { start: number; length: number },
): Item {
  const start = Math.min(...members.map((e) => e.at))
  const end = Math.max(...members.map(endOf))
  const tools = members.filter((e) => e.kind === 'tool')
  const type = session.subagents.find((a) => a.agent_id === id)?.agent_type
  return {
    start,
    end,
    row: {
      type: 'agent',
      key: `a-${id}`,
      id,
      name: type ?? 'Subagent',
      calls: tools.length,
      failed: tools.filter((e) => isFailed(e.status)).length,
      total: tools.reduce((sum, e) => sum + (e.duration_seconds ?? 0), 0),
      bar: barOf(axis, start, end),
      rows: withGaps(members.map((e) => entryItem(e, session, axis))),
    },
  }
}

/** A turn's rows: its own entries in order, each subagent's entries gathered under one row where
 * its first entry stands, and a gap row before anything that starts after an idle stretch. Bars
 * are relative to the turn's axis, from its first entry to the end of its last call. */
export function traceRows(turn: Turn, session: Session): Row[] {
  const axis = axisOf(turn)
  const members = new Map<string, Entry[]>()
  for (const e of turn.entries) {
    if (e.agent_id) members.set(e.agent_id, [...(members.get(e.agent_id) ?? []), e])
  }
  const items: Item[] = []
  const placed = new Set<string>()
  for (const e of turn.entries) {
    if (!e.agent_id) items.push(entryItem(e, session, axis))
    else if (!placed.has(e.agent_id)) {
      placed.add(e.agent_id)
      items.push(agentItem(e.agent_id, members.get(e.agent_id) ?? [], session, axis))
    }
  }
  return withGaps(items)
}

/** A turn's axis length in seconds: from its first entry to the end of its last call. */
export function axisLength(turn: Turn): number {
  return axisOf(turn).length
}
