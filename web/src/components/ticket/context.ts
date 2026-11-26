// What the ticket form shares with its sections: the fields being edited, and how a change is
// sent while every control that sends one is disabled.

import { inject, ref, type InjectionKey, type Ref } from 'vue'
import { act } from '../../lib/actions'
import { perform } from '../../lib/notice'
import { usePressed, type Pressed } from '../../lib/pressed'
import type { Field } from '../../lib/ticket'

export interface TicketForm extends Pressed {
  /** The fields as typed; each saves itself when changed. */
  model: Record<Field, string>
  /** Send the changed fields; `field` is the one just changed, which a refusal is shown under. */
  save: (field?: string) => Promise<void>
  /** The board's reason for each field it refused, by field, until that field is saved. */
  errors: Readonly<Ref<Partial<Record<string, string>>>>
  /** Whether a change is being sent. */
  busy: Readonly<Ref<boolean>>
  /** The ticket's address in the API. */
  base: Readonly<Ref<string>>
  /** Read the ticket and the board again, keeping the fields as typed. */
  refresh: () => Promise<void>
  /** Run a change with `busy` set until it ends. */
  task: <T>(work: () => Promise<T>) => Promise<T>
  /** Post to a path under the ticket; whether the board took it. */
  send: (path: string, body: object) => Promise<boolean>
}

export const TICKET_FORM: InjectionKey<TicketForm> = Symbol('ticket form')

/** The heading level of the form's sections: one below the page's h1 or the panel's h2 title. */
export const SECTION_LEVEL: InjectionKey<Readonly<Ref<number>>> = Symbol('section level')

/** The heading level of the form's sections, 2 outside a form that says otherwise. */
export const useSectionLevel = (): Readonly<Ref<number>> => inject(SECTION_LEVEL, ref(2))

/** The form's busy state, and how a change is run and sent under it, naming the button pressed. */
export function useTicketTasks(base: Readonly<Ref<string>>, refresh: () => Promise<void>) {
  const busy = ref(false)
  async function task<T>(work: () => Promise<T>): Promise<T> {
    busy.value = true
    try {
      return await work()
    } finally {
      busy.value = false
    }
  }
  const send = (path: string, body: object): Promise<boolean> =>
    task(() => perform(() => act('POST', `${base.value}/${path}`, body), refresh))
  return { busy, task, send, ...usePressed() }
}

/** The form a section renders in. */
export function useTicketForm(): TicketForm {
  const form = inject(TICKET_FORM)
  if (!form) throw new Error('A ticket section renders inside the ticket form')
  return form
}
