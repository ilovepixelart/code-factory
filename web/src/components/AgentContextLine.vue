<script setup lang="ts">
import { computed } from 'vue'
import type { AgentDefinition } from '../generated/AgentDefinition'
import { dayClock } from '../lib/format'
import { contextLine, type Last } from '../lib/roster'

// An agent card's line on the owner's context (CF-1163): its size, never its text, and which
// version its last run received.
const props = defineProps<{ agent: AgentDefinition; last: Last | undefined; now: number }>()

const context = computed(() =>
  contextLine(props.agent, props.last, (at) => dayClock(at, props.now)),
)
</script>

<template>
  <p v-if="context" class="text-muted-foreground text-sm" data-context>
    {{ context.size }}<template v-if="context.next">, its next run receives it</template
    ><template v-if="context.received"
      >{{ context.next ? ';' : ',' }} last run
      <span class="font-mono text-sm">{{ context.received.run }}</span> ({{
        context.received.ticket
      }}) received the version of {{ context.received.at }}</template
    >
  </p>
</template>
