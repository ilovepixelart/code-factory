<script setup lang="ts">
import { cn } from 'cn'
import { computed } from 'vue'
import { STAGE_LABELS, STAGE_TONE, type Stage } from '../lib/board'

// A stage as a glyph that fills as the work moves along: Spec an empty ring, Build half filled,
// Review three quarters, Merged (and Released, in the muted tone) a filled circle with a check.
// `decorative` hides it from a screen reader where the stage's word stands beside it.
const { stage, decorative } = defineProps<{ stage: Stage; decorative?: boolean }>()

type Shape = 'ring' | 'half' | 'three-quarters' | 'done'
const SHAPES: Record<Stage, Shape> = {
  spec: 'ring',
  build: 'half',
  review: 'three-quarters',
  merged: 'done',
  released: 'done',
}
// The filled part inside the ring, from twelve o'clock clockwise, as a pie around the centre.
const PIES: Partial<Record<Shape, string>> = {
  half: 'M8 8V4.5a3.5 3.5 0 0 1 0 7Z',
  'three-quarters': 'M8 8V4.5a3.5 3.5 0 1 1-3.5 3.5Z',
}
const shape = computed(() => SHAPES[stage])
</script>

<template>
  <svg
    viewBox="0 0 16 16"
    :class="cn('size-3.5 shrink-0', STAGE_TONE[stage])"
    :data-shape="shape"
    :role="decorative ? undefined : 'img'"
    :aria-label="decorative ? undefined : STAGE_LABELS[stage]"
    :aria-hidden="decorative ? 'true' : undefined"
  >
    <template v-if="shape === 'done'">
      <circle cx="8" cy="8" r="7" fill="currentColor" />
      <path
        data-check
        d="M5.2 8.2l1.9 1.9 3.7-3.9"
        fill="none"
        stroke="var(--background)"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </template>
    <template v-else>
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.5" />
      <path v-if="PIES[shape]" :d="PIES[shape]" fill="currentColor" />
    </template>
  </svg>
</template>
