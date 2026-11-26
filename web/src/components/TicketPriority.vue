<script setup lang="ts">
import { sentence } from '../lib/format'
// A ticket's priority on its card: the word, and a mark for it (an exclamation for urgent, else up
// to three bars filled by how high it is).
defineProps<{ priority: string }>()

const PRIORITY_TEXT: Record<string, string> = {
  urgent: 'text-destructive font-medium',
  high: 'text-foreground font-medium',
  medium: 'text-muted-foreground',
  low: 'text-muted-foreground',
}
const FILLED: Record<string, number> = { high: 3, medium: 2, low: 1 }
</script>

<template>
  <span class="flex items-center gap-1" :class="PRIORITY_TEXT[priority]" title="Priority"
    >{{ sentence(priority)
    }}<span
      v-if="priority === 'urgent'"
      class="grid size-3.5 place-items-center rounded-xs bg-destructive/10 text-sm leading-none font-bold text-destructive"
      aria-hidden="true"
      >!</span
    ><svg v-else class="size-3.5" viewBox="0 0 14 14" aria-hidden="true">
      <rect
        v-for="i in [0, 1, 2]"
        :key="i"
        :x="1 + i * 4.5"
        :y="9 - i * 3.5"
        width="3"
        :height="4 + i * 3.5"
        rx="0.75"
        fill="currentColor"
        :opacity="i < (FILLED[priority] ?? 0) ? 1 : 0.25"
      /></svg
  ></span>
</template>
