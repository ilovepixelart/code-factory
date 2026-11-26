// An open question as the server lists it, and what
// is picked while it is answered.

interface Choice {
  text: string
  recommended: boolean
  /** Why it is recommended, on a question asked before `description` existed. */
  reason: string
  /** What picking it means. */
  description?: string
  /** A mockup or code to compare, shown as monospace text. */
  preview?: string
  ticked: boolean
}

/** What a choice's card says under its label: its description, else why it is recommended. */
export const explained = (choice: Choice): string =>
  choice.description === undefined || choice.description === '' ? choice.reason : choice.description

export interface Asked {
  document: string
  index: number
  text: string
  /** A label of a few words naming what it is about. */
  topic?: string
  choices: Choice[]
  several: boolean
}

/** The choices picked, or Other with its text (`null` while Other is not chosen). */
export interface Picking {
  choices: string[]
  other: string | null
}

export const NOTHING_PICKED: Picking = { choices: [], other: null }

/** Whether a picking can be sent: a choice picked, or Other holding text. */
export const ready = (picking: Picking | undefined): boolean =>
  picking !== undefined &&
  (picking.other === null ? picking.choices.length > 0 : picking.other.trim() !== '')

/** The answers request for `asked`: what names the question, then what answers it. */
export const answerBody = (
  asked: Asked | null | undefined,
  given: { choices: string[] } | { answer: string },
) => ({ document: asked?.document, index: asked?.index, question: asked?.text, ...given })

/** The choice a question recommends, when it is answered by one choice and names one. */
export const recommendedOf = (asked: Asked | null | undefined): string | null =>
  asked && !asked.several ? (asked.choices.find((c) => c.recommended)?.text ?? null) : null

/** The answer request's part for a picking: its choices, or Other's text as the answer. */
export const reply = (picking: Picking): { choices: string[] } | { answer: string } =>
  picking.other === null ? { choices: picking.choices } : { answer: picking.other }
