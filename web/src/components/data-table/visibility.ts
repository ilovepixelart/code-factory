// The columns a viewer shows or hides through the Columns menu, kept in this browser under `key`
// so the next visit opens with the same ones; without a key, they reset on each visit.

import type { ColumnVisibilityState, Updater } from '@tanstack/vue-table'
import { shallowRef, type ShallowRef } from 'vue'
import { load, save } from '../../lib/storage'

export function useColumnVisibility(key: string): {
  state: ShallowRef<ColumnVisibilityState>
  change: (next: Updater<ColumnVisibilityState>) => void
} {
  const state = shallowRef<ColumnVisibilityState>(key ? load(key, {}) : {})
  return {
    state,
    change(next) {
      state.value = typeof next === 'function' ? next(state.value) : next
      if (key) save(key, state.value)
    },
  }
}
