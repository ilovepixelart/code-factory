<script setup lang="ts">
import { cn } from 'cn'

// A label's or a stage's dot. The chart tokens run from near white to near black, so the darkest
// vanish on a dark chip and the lightest on a light one: a faint ring keeps every one in view.
const { color } = defineProps<{ color: string }>()
</script>

<template>
  <span
    :class="cn('size-2 shrink-0 rounded-full ring-1 ring-foreground/30', color)"
    data-color-dot
    aria-hidden="true"
  ></span>
</template>
