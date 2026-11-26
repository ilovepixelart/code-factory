<script setup lang="ts">
import { BotIcon, Clock01Icon, HelpCircleIcon, StopIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { STAGE_LABELS, type Card } from '../lib/board'
import { haltWords, resumes, short } from '../lib/format'
import StatusBadge from './StatusBadge.vue'
import Subagent from './ai/Subagent/Subagent.vue'
import { Trace } from '@/components/ui/trace'

// What holds or runs a card: its open questions, a stopped agent, a usage limit, its agent runs,
// sessions and session subagents; nothing when none.
const { card } = defineProps<{ card: Card }>()

const showBadges = computed(
  () =>
    card.open_questions > 0 ||
    card.runs.length > 0 ||
    card.sessions.length > 0 ||
    card.subagents.length > 0 ||
    card.halted !== '' ||
    card.limited_until !== null,
)
const limitText = computed(() =>
  card.limited_until === null ? '' : resumes(card.limited_until, Date.now() / 1000),
)

const seconds = (): number => Date.now() / 1000

const haltText = computed(() => haltWords(card.halted))
// A session that ended says nothing about the ticket now (CF-1076).
const liveSessions = computed(() => card.sessions.filter((s) => s.state !== 'ended'))
</script>

<template>
  <div v-if="showBadges" class="flex flex-wrap gap-1.5">
    <StatusBadge
      v-if="card.open_questions"
      key="questions"
      tone="warning"
      title="The agent waits for an answer"
      ><HugeiconsIcon :icon="HelpCircleIcon" data-icon="inline-start" aria-hidden="true" />{{
        card.open_questions
      }}
      open question{{ card.open_questions !== 1 ? 's' : '' }}</StatusBadge
    >
    <StatusBadge v-if="card.halted" key="halted" tone="warning"
      ><HugeiconsIcon :icon="StopIcon" data-icon="inline-start" aria-hidden="true" />{{
        haltText
      }}</StatusBadge
    >
    <StatusBadge
      v-if="limitText"
      key="limit"
      tone="warning"
      title="The runtime's usage limit was reached; the same column starts again after its reset"
      ><HugeiconsIcon :icon="Clock01Icon" data-icon="inline-start" aria-hidden="true" />Usage limit:
      {{ limitText }}</StatusBadge
    >
    <StatusBadge v-for="run in card.runs" :key="run.id" tone="info"
      ><HugeiconsIcon :icon="BotIcon" data-icon="inline-start" aria-hidden="true" />Agent ·
      {{ STAGE_LABELS[run.stage]
      }}<template v-if="run.attempt > 0"> · attempt {{ run.attempt }}</template> · iteration
      {{ run.iteration
      }}<template v-if="run.loop"> of {{ run.max_iterations }}</template></StatusBadge
    >
    <RouterLink
      v-for="s in liveSessions"
      :key="s.session_id"
      :to="`/sessions/${s.session_id}`"
      class="flex items-center gap-1.5 text-sm"
      ><StatusBadge :state="s.state" /><span class="text-muted-foreground"
        >session <span class="font-mono">{{ short(s.session_id) }}</span></span
      ></RouterLink
    >
    <Trace v-if="card.subagents.length" key="subagents">
      <Subagent
        v-for="agent in card.subagents"
        :key="agent.agent_id"
        :agent="agent"
        :now="seconds()"
      />
    </Trace>
  </div>
</template>
