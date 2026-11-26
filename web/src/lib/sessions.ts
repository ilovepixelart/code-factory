// Agent sessions as `/api/sessions` and a session's timeline answer them, and their turns.

interface Action {
  tool: string
  summary: string
  started_at: number
}

interface Subagent {
  agent_id: string
  agent_type: string
  running: boolean
  /** Running with a call open and silent past the stale limit; it then has no current action. */
  stale: boolean
  current_action: Action | null
}

export interface Session {
  session_id: string
  cwd: string
  repository: string
  branch: string
  state: string
  last_event_at: number
  stale: boolean
  current_action: Action | null
  subagents: Subagent[]
  last_prompt: string
  turn_tool_calls: number
  /** What it is on, from its events (CF-1380); empty before its first tool call. */
  doing?: string
  /** When the call that line names began, set only for `last call: ...`. */
  doing_since?: number | null
}

export interface Usage {
  input: number
  output: number
  cache_read: number
  cache_write: number
  cost: number | null
  reported_at: number | null
  cost_incomplete: boolean
}

export interface Entry {
  kind: string
  seq: number
  at: number
  agent_id: string | null
  title: string
  detail: string
  duration_seconds: number | null
  status: string
}

export interface Turn {
  index: number
  prompt_text: string
  entries: Entry[]
  started_at: number
  duration_seconds: number | null
  calls: number
  /** Calls that failed or were denied; they do not change the turn's outcome. */
  failed_calls: number
  outcome: string
  open_by_default: boolean
  /** The first turn shown, whose prompt is among the entries not shown. */
  continued: boolean
}

const FAILED = new Set(['failed', 'denied'])

/** A call that failed or was denied. */
export function isFailed(status: string): boolean {
  return FAILED.has(status)
}

function turnOf(index: number, group: Entry[], latest: boolean): Turn {
  const tools = group.filter((e) => e.kind === 'tool')
  const failedCalls = tools.filter((e) => isFailed(e.status)).length
  const running = latest && !group.some((e) => e.kind === 'stop')
  const startedAt = group[0]?.at ?? 0
  return {
    index,
    prompt_text: group.find((e) => e.kind === 'prompt')?.detail ?? '',
    entries: group,
    started_at: startedAt,
    duration_seconds: running ? null : (group.at(-1)?.at ?? startedAt) - startedAt,
    calls: tools.length,
    failed_calls: failedCalls,
    outcome: running ? 'running' : 'done',
    open_by_default: latest || failedCalls > 0,
    continued: false,
  }
}

/** Entries grouped into turns: each prompt starts one. With no `earlierPrompts`, what precedes
 * the first prompt joins it; otherwise it continues turn `earlierPrompts`, and the turns after it
 * are numbered from there. */
export function turns(entries: Entry[], earlierPrompts = 0): Turn[] {
  const groups: Entry[][] = []
  for (const entry of entries) {
    const last = groups.at(-1)
    const starts =
      entry.kind === 'prompt' && (earlierPrompts > 0 || last?.some((e) => e.kind === 'prompt'))
    if (starts || !last) groups.push([entry])
    else last.push(entry)
  }
  const continued = earlierPrompts > 0 && groups[0]?.[0]?.kind !== 'prompt'
  const first = continued ? earlierPrompts : earlierPrompts + 1
  return groups.map((group, i) => ({
    ...turnOf(first + i, group, i + 1 === groups.length),
    continued: continued && i === 0,
  }))
}

/** `GET /api/sessions` asked for a page (CF-1194): every blocked session, then the page of the
 * rest, grouped by repository in the server's order. `rows` hold the state asked for (CF-1265);
 * `counts` are the sessions under each state and `repositories` the rows of each repository
 * under that state, over every page. */
export interface PagedSessions {
  waiting: Session[]
  rows: Session[]
  total: number
  page: number
  size: number
  ended_hidden: number
  counts: Record<'waiting' | 'working' | 'idle' | 'stale', number>
  repositories: Record<string, number>
}

/** A page's sessions in runs of one repository, in the order the server gave them. */
export function inRuns(sessions: Session[]): [string, Session[]][] {
  const runs: [string, Session[]][] = []
  for (const s of sessions) {
    const name = s.repository || 'unknown repository'
    const last = runs.at(-1)
    if (last?.[0] === name) last[1].push(s)
    else runs.push([name, [s]])
  }
  return runs
}

/** A stored payload as indented JSON: a field trimmed at capture (`{head, _trimmed_chars}`)
 * shows its head and an ellipsis, and its length is listed in `cut`. */
export function payloadText(value: unknown): { text: string; cut: number[] } {
  const cut: number[] = []
  const shown = (part: unknown): unknown => {
    if (Array.isArray(part)) return part.map(shown)
    if (part === null || typeof part !== 'object') return part
    const fields = part as Record<string, unknown>
    if (typeof fields.head === 'string' && '_trimmed_chars' in fields) {
      cut.push(Number(fields._trimmed_chars))
      return `${fields.head}…`
    }
    return Object.fromEntries(Object.entries(fields).map(([key, field]) => [key, shown(field)]))
  }
  return { text: JSON.stringify(shown(value), null, 2), cut }
}
