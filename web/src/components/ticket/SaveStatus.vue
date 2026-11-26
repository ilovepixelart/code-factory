<script setup lang="ts">
import { NOT_SAVED } from '../../lib/ticket'

// The footer's word for the last save; a refusal is in the error colour.
defineProps<{ saved: string }>()
</script>

<template>
  <span
    class="ml-auto text-sm"
    :class="saved === NOT_SAVED ? 'text-destructive' : 'text-foreground'"
    aria-live="polite"
    >{{ saved }}</span
  >
</template>
