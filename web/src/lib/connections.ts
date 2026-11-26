// What the Agents page reads and sends about connections.

import type { ConnectionDefinition } from '../generated/ConnectionDefinition'
import type { Found } from '../generated/Found'
import type { Kind } from '../generated/Kind'
import { CONTEXT_FLOOR } from '../generated/Limits'
import type { Model } from '../generated/Model'
import type { Status } from '../generated/Status'

export type { Kind, Model }
/** Whether a connection answers, its models, or why not. */
export type Checked = Status
/** A model server found on this machine. */
export type FoundServer = Found

/** A connection as the list answers it: whether its key variable holds a value, never the value. */
export type ListedConnection = ConnectionDefinition & { key_set: boolean; here: boolean }

export interface ConnectionList {
  connections: ListedConnection[]
  kinds: Kind[]
  problem: string
}

export interface ConnectionStatus {
  connections: Checked[]
  local: FoundServer[]
  /** What the check says of each agent's model, by the agent's name (`connections::reach`). */
  reach: Record<string, Reach>
}

/** A connection as its form holds it. */
export interface ConnectionDraft {
  name: string
  kind: string
  base_url: string
  key_env: string
}

/** The form's start for a connection, or for a new one of `kind` at `address`. */
export function connectionDraftOf(
  connection: ConnectionDefinition | null,
  kind = 'lm-studio',
  address = '',
): ConnectionDraft {
  if (!connection) return { name: '', kind, base_url: address, key_env: '' }
  return { ...connection }
}

/** What an add or a change sends for a draft. */
export function connectionBodyOf(draft: ConnectionDraft): object {
  return {
    name: draft.name.trim(),
    kind: draft.kind,
    base_url: draft.base_url.trim(),
    key_env: draft.key_env.trim(),
  }
}

const THIS_MACHINE = new Set(['localhost', '127.0.0.1', '[::1]'])

/**
 * Whether two addresses reach the same server: the same scheme, port and path, and the same host
 * or both this machine's (CF-480); false for an address that does not parse.
 */
export function sameServer(one: string, other: string): boolean {
  if (!URL.canParse(one) || !URL.canParse(other)) return one === other
  const [a, b] = [new URL(one), new URL(other)]
  const host =
    a.hostname === b.hostname || (THIS_MACHINE.has(a.hostname) && THIS_MACHINE.has(b.hostname))
  const path = (url: URL) => url.pathname.replace(/\/+$/, '')
  return host && a.protocol === b.protocol && a.port === b.port && path(a) === path(b)
}

/** A kind's label, or the kind itself when the board does not know it. */
export function kindLabel(kinds: Kind[], kind: string): string {
  return kinds.find((k) => k.kind === kind)?.label ?? kind
}

/** A model's context length and the context it is loaded with, empty when the server reports neither. */
export function contextText(model: Model): string {
  const parts = [
    model.context === null ? '' : `${model.context.toLocaleString('en')} tokens`,
    model.loaded === null ? '' : `loaded at ${model.loaded.toLocaleString('en')}`,
  ]
  return parts.filter((part) => part !== '').join(', ')
}

/**
 * Whether a run of the model would get less context than it needs: the context it is loaded
 * with, or its length while not loaded (CF-389, CF-529).
 */
export function underFloor(model: Model): boolean {
  const held = model.loaded ?? model.context
  return held !== null && held < CONTEXT_FLOOR
}

/** The models each connection answered with, by its name. */
export function modelsByConnection(status: ConnectionStatus): Record<string, string[]> {
  return Object.fromEntries(status.connections.map((c) => [c.name, c.models.map((m) => m.id)]))
}

/**
 * What an agent's card says of its connection, empty for an agent with none (CF-378); a model
 * loaded with less context than a run needs says how much it has (CF-389).
 */
export type Reach =
  | ''
  | 'checking'
  | 'answers'
  | 'does not answer'
  | 'key missing'
  | 'model not listed'
  | `context ${string} of ${string}`

/** Whether a card's word says its agent cannot run now. */
export function needsAttention(reach: Reach): boolean {
  return !['', 'checking', 'answers'].includes(reach)
}

/**
 * Whether `agent` reaches its model through its connection: its key variable from the list,
 * then what the last finished check says of it, worded by the server; `checking` while a check
 * runs, empty while no check has answered.
 */
export function reachOf(
  agent: { name: string; connection: string },
  list: ConnectionList | null,
  status: ConnectionStatus | null,
  checking = false,
): Reach {
  if (!agent.connection) return ''
  const defined = list?.connections.find((c) => c.name === agent.connection)
  if (defined?.key_env && !defined.key_set) return 'key missing'
  if (checking) return 'checking'
  return status?.reach[agent.name] ?? ''
}

/** Whether `agent`'s connection is served on this machine, where its model can be checked (CF-401). */
export function runsHere(agent: { connection: string }, list: ConnectionList | null): boolean {
  return list?.connections.find((c) => c.name === agent.connection)?.here ?? false
}
