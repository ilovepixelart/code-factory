// What the shell shares so a page and the command menu open the same forms and act on the same
// ticket. The ticket shown in the ticket panel, which has no address of its own: the command menu acts on
// it, as on the ticket page, which the route names.

import { ref, type InjectionKey } from 'vue'

export interface TicketRef {
  repository: string
  id: string
}

export const panelTicket = ref<TicketRef | null>(null)

/** Opens the new ticket form, which the shell holds so every page and the command menu reach it. */
export const NEW_TICKET: InjectionKey<() => void> = Symbol('new ticket')
