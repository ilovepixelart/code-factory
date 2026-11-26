// Changes to one ticket that a button and a command menu entry both send.

import type { Changed } from '../generated/Changed'
import { act } from './actions'

/** The ticket's address in the API. */
export const ticketPath = (repository: string, id: string): string =>
  `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}`

/** Start an agent on the ticket with the permissions and loop of the Status section's button. */
export function startAgent(base: string): Promise<Changed> {
  return act('POST', `${base}/runs`, { permissions: 'bypassPermissions', loop: true })
}

/** Archive the ticket, or restore it; `changed` are fields sent with it. */
export function setArchived(
  base: string,
  archived: boolean,
  changed: object = {},
): Promise<Changed> {
  return act('PATCH', base, { ...changed, archived: archived ? 'true' : '' })
}
