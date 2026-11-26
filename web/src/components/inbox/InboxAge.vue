<script setup lang="ts">
import { clock, span } from '../../lib/format'

// A null `since` is a wait with no recorded start: it shows no age (CF-412).
const { since, now } = defineProps<{ since: number | null; now: number }>()
</script>

<template>
  <span
    v-if="since !== null"
    class="text-muted-foreground ml-auto shrink-0 text-sm tabular-nums"
    :title="`Waiting since ${clock(since)}`"
    >{{ span(now - since) }}</span
  >
</template>
