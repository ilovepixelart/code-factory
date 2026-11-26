<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

// AI Elements' Suggestion row: one line that scrolls sideways when the suggestions do not fit,
// fading the edge that has more to show.
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
defineSlots<{ default?: () => unknown }>()
</script>

<template>
  <div
    :class="
      cn('no-scrollbar flex scroll-fade-x gap-2 overflow-x-auto overscroll-x-contain', props.class)
    "
  >
    <slot />
  </div>
</template>
