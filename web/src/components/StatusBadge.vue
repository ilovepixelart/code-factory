<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { statusTone, statusWord, TONE_VARIANTS, type BadgeTone } from '../lib/status_tone'

// The one status mark (docs/design.md, Theme): a status word on a Badge. `state` gives both the tone
// (the status map) and the word (sentence case); `tone` and the slot are for a status the map does
// not know. `quiet` keeps the words on the quiet badge, for a page where only what needs the owner
// carries a colour (CF-1162).
const {
  state = '',
  tone = null,
  quiet,
} = defineProps<{
  state?: string
  tone?: BadgeTone | null
  quiet?: boolean
}>()
defineSlots<{ default?: () => unknown }>()

const variant = computed(() => TONE_VARIANTS[quiet ? 'quiet' : (tone ?? statusTone(state))])
</script>

<template>
  <Badge :variant="variant"
    ><slot>{{ statusWord(state) }}</slot></Badge
  >
</template>
