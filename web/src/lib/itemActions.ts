// One change per queue item, sent through the board's undoable routes: its control disabled while
// it is sent, a refusal kept under the item (CF-1171-R7).

import { reactive } from 'vue'
import { act } from './actions'
import { announce, refusalText } from './notice'

export function itemActions(changed: () => void) {
  const busy = reactive(new Set<string>())
  const errors = reactive<Record<string, string>>({})

  async function run(key: string, method: 'POST' | 'PATCH', path: string, body: object = {}) {
    busy.add(key)
    errors[key] = ''
    try {
      announce(await act(method, path, body))
      changed()
    } catch (error) {
      errors[key] = refusalText(error)
    } finally {
      busy.delete(key)
    }
  }

  return { busy, errors, run }
}

/** The address of an entry's routes. */
export const entryPath = (repository: string, id: string): string =>
  `/api/memory/${encodeURIComponent(repository)}/${encodeURIComponent(id)}`
