// A new ticket's description follows its type's template until the person writes in it: "written
// in" compares the text with the last template
// put there.

import { readJson } from './actions'

/** The description after a new template arrives: the template while the text is untouched. */
export function followTemplate(text: string, last: string, template: string): string {
  return text === last ? template : text
}

/** A repository's template for a type, empty when there is none or it cannot be read. */
export async function templateFor(repository: string, type: string): Promise<string> {
  const answer = await readJson<{ text?: unknown }>(
    `/api/repositories/${encodeURIComponent(repository)}/templates/${encodeURIComponent(type)}`,
  )
  return typeof answer?.text === 'string' ? answer.text : ''
}
