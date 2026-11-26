<script setup lang="ts">
import type { Meter } from '../lib/roster'
import Context from './ai/Context/Context.vue'

// An agent's use of each limit while it holds a ticket: one Context per limit, named for the agent
// and the limit, in the variant its share calls for.
defineProps<{ name: string; meters: Meter[] }>()
</script>

<template>
  <div v-if="meters.length" class="flex flex-wrap gap-2">
    <Context
      v-for="meter in meters"
      :key="meter.limit"
      :name="`${name} ${meter.limit}`"
      :label="meter.limit"
      :used="meter.used"
      :max="meter.max"
      :text="meter.text"
      :tone="meter.tone"
    />
  </div>
</template>
