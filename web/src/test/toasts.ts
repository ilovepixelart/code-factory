// The app's toasts as App.vue mounts them: the notice and the reload offer shown through
// vue-sonner's Toaster, refreshing the provided board after an Undo.

import { defineComponent, h, inject } from 'vue'
import { Toaster } from '@/components/ui/sonner'
import { BOARD } from '../lib/live'
import { useNoticeToasts } from '../lib/noticeToasts'

export const Toasts = defineComponent({
  setup() {
    const live = inject(BOARD, null)
    useNoticeToasts(() => live?.refresh() ?? Promise.resolve())
    return () => h(Toaster)
  },
})
