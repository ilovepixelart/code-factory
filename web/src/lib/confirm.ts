// The page's own confirmation dialog: a change that
// cannot be taken back is sent only once the person presses its confirming button.

import { reactive } from 'vue'

/** What the dialog asks about: Delete ticket by default, Remove agent or connection otherwise. */
export interface Asking {
  title: string
  verb: string
}

const DELETE: Asking = { title: 'Delete ticket', verb: 'Delete' }

export const question = reactive({
  text: '',
  title: DELETE.title,
  verb: DELETE.verb,
  answer: null as ((yes: boolean) => void) | null,
})

/** Ask; resolves true only when the person confirms. */
export function confirm(text: string, asking: Asking = DELETE): Promise<boolean> {
  question.answer?.(false)
  return new Promise((resolve) => {
    Object.assign(question, { text, ...asking, answer: resolve })
  })
}

export function answer(yes: boolean): void {
  const resolve = question.answer
  Object.assign(question, { text: '', answer: null })
  resolve?.(yes)
}
