// Cards chosen for a bulk action: kept here, so the selection
// survives the board's refreshes; a card that left the board leaves the selection.

import { reactive } from 'vue'

/** The chosen cards as `repository/id`. */
export const chosen = reactive(new Set<string>())

export const keyOf = (repository: string, id: string): string => `${repository}/${id}`

/** Keep only the chosen cards still `present`. */
export function keepPresent(selection: Set<string>, present: Iterable<string>): void {
  const shown = new Set(present)
  for (const key of [...selection]) if (!shown.has(key)) selection.delete(key)
}

export function toggle(key: string): void {
  if (chosen.has(key)) chosen.delete(key)
  else chosen.add(key)
}

export function clearSelection(): void {
  chosen.clear()
}
