// How the Sessions page reads a session: its state as the person sees it, what it is doing and
// the repository and branch it is on (CF-1204).

import { span, trim } from './format'
import type { Entry, Session } from './sessions'

/** The filter chips, in the order they show: a session's state, stale apart from the rest. */
export const STATE_FILTERS = ['waiting', 'working', 'idle', 'stale'] as const
export type StateFilter = (typeof STATE_FILTERS)[number]

/** The chip a session counts under; an ended one under none. */
export function stateOf(session: Session): StateFilter | null {
  if (session.state === 'blocked') return 'waiting'
  if (session.stale) return 'stale'
  return session.state === 'working' || session.state === 'idle' ? session.state : null
}

/** The chip an address names, or null for every state. */
export function filterOf(value: unknown): StateFilter | null {
  return STATE_FILTERS.find((state) => state === value) ?? null
}

/** `text` with every path inside the session's folder written from that folder; a folder that is
 * the root (or none) leaves the text as it is. */
export function fromFolder(text: string, cwd: string): string {
  const folder = cwd.replace(/\/+$/, '')
  return folder ? text.replaceAll(`${folder}/`, '') : text
}

/** What the session is doing now in one line: its open tool call, else its last prompt. */
export function doing(session: Session): string {
  const action = session.current_action
  if (action) return trim(fromFolder(`${action.tool} ${action.summary}`, session.cwd), 160)
  return trim(session.last_prompt, 160)
}

/** What a Sessions row says: the line the server worked out from the events, with how long ago
 * its last call began, else [`doing`]. */
export function rowLine(session: Session, now: number): string {
  if (!session.doing) return doing(session)
  const ago = session.doing_since == null ? '' : `, ${span(now - session.doing_since)} ago`
  return trim(fromFolder(session.doing, session.cwd), 160) + ago
}

/** Where the session works when no ticket owns it: its repository and branch. */
export function placeOf(session: Session): string {
  const repository = session.repository || 'unknown repository'
  return session.branch ? `${repository} on ${session.branch}` : repository
}

/** The status an entry shows: an open call of a stale session, or of a subagent that is stale or no
 * longer running, is not drawn as running. */
export function entryStatus(entry: Entry, session: Session): string {
  if (entry.status !== 'running') return entry.status
  if (!entry.agent_id) return session.stale ? 'stale' : entry.status
  const agent = session.subagents.find((a) => a.agent_id === entry.agent_id)
  if (!agent) return entry.status
  if (!agent.running) return 'interrupted'
  return agent.stale ? 'stale' : entry.status
}
