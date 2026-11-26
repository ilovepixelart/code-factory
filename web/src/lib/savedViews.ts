import { ref } from 'vue'
import { act, ask, post, Refused } from './actions'
import { refused } from './notice'

interface SavedView {
  name: string
  query: string
}

const views = ref<SavedView[]>([])

export function viewUrl(view: SavedView): string {
  return view.query ? `/tickets?${view.query}` : '/tickets'
}

export function useSavedViews() {
  async function refresh(): Promise<void> {
    try {
      const answer = await ask<unknown>('/api/views')
      if (
        !Array.isArray(answer) ||
        !answer.every(
          (view: unknown) =>
            typeof view === 'object' &&
            view !== null &&
            'name' in view &&
            typeof view.name === 'string' &&
            'query' in view &&
            typeof view.query === 'string',
        )
      ) {
        throw new Refused('Saved views could not be read')
      }
      views.value = answer as SavedView[]
    } catch (error) {
      refused(error)
    }
  }

  async function save(name: string, query: string): Promise<boolean> {
    try {
      await post('/api/views', { name, query })
      await refresh()
      return true
    } catch (error) {
      refused(error)
      return false
    }
  }

  async function remove(name: string): Promise<void> {
    try {
      await act('DELETE', `/api/views/${encodeURIComponent(name)}`)
      await refresh()
    } catch (error) {
      refused(error)
    }
  }

  return { views, refresh, save, remove }
}
