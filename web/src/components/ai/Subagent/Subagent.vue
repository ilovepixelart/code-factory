<script setup lang="ts">
import { BotIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { AtWork } from '../../../generated/AtWork'
import { span } from '../../../lib/format'
import { TraceDescription, TraceIcon, TraceLine, TraceTitle } from '@/components/ui/trace'

// AI Elements' Subagent while it runs, over a session subagent at work on a ticket (CF-1184): its
// name and open tool call as a running line, how long its run has lasted after the title, and a
// link to its session. The board knows only the call open now, not the calls so far, so the line
// has no content to expand and links out instead. The title carries the whole text it truncates.
const { agent, now } = defineProps<{ agent: AtWork; now: number }>()
const age = computed(() => span(now - agent.since))
</script>

<template>
  <RouterLink
    :to="`/sessions/${agent.session_id}`"
    :title="`${agent.name}: ${agent.doing}, for ${age}`"
  >
    <TraceLine status="running">
      <TraceIcon><HugeiconsIcon :icon="BotIcon" /></TraceIcon>
      <TraceTitle>Running {{ agent.name }}: {{ agent.doing }}</TraceTitle>
      <TraceDescription>{{ age }}</TraceDescription>
    </TraceLine>
  </RouterLink>
</template>
