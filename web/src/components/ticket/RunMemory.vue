<script setup lang="ts">
import { computed } from 'vue'
import { dayClock } from '../../lib/format'
import type { RunMemory } from '../../lib/ticket'

// What a run was given (CF-1200): the memory entries recall gave it, each linking to the Memory
// page, those it left out for the budget, and the version of the owner's context; never the text.
const {
  memory,
  contextAt = null,
  now,
} = defineProps<{
  memory: RunMemory | null | undefined
  contextAt?: number | null
  now: number
}>()

const received = computed(() => memory?.received ?? [])
const leftOut = computed(() => memory?.left_out.length ?? 0)
</script>

<template>
  <p class="text-muted-foreground w-full text-sm" data-run-memory>
    <template v-if="received.length"
      >Memory: {{ received.length }} entr{{ received.length === 1 ? 'y' : 'ies' }}
      <template v-for="(id, index) in received" :key="id"
        ><template v-if="index">, </template
        ><RouterLink
          :to="`/memory#${id}`"
          class="underline-offset-4 hover:underline font-mono text-sm"
          >{{ id }}</RouterLink
        ></template
      ><template v-if="leftOut"> · {{ leftOut }} left out for the budget</template></template
    ><template v-else>No memory</template
    ><template v-if="contextAt !== null"> · Context of {{ dayClock(contextAt, now) }}</template>
  </p>
</template>
