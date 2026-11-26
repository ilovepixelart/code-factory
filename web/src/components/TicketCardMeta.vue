<script setup lang="ts">
import PullSize from './PullSize.vue'
import StatusBadge from './StatusBadge.vue'
import {
  Calendar03Icon,
  Cancel01Icon,
  Clock01Icon,
  GitPullRequestIcon,
  KanbanIcon,
  Tick02Icon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { STAGE_LABELS, pullNumber, queueWords, type Card, type Stage } from '../lib/board'
import { cost, day, money, spendTitle } from '../lib/format'
import PullLabel from './PullLabel.vue'

// A board card's line of facts: due date, checklist, children, age, evidence, checks, pull
// request, spend and queue; nothing when the card has none of them.
const { card, stage, today, age } = defineProps<{
  card: Card
  stage: Stage
  today: string
  age: number | null
}>()

const done = computed(() => card.checklist[0])
const total = computed(() => card.checklist[1])
const children = computed(() => card.links?.children ?? 0)
const childrenDone = computed(() => card.links?.children_done ?? 0)
const checkCommit = computed(() => (card.check ? `On ${card.check.commit.slice(0, 7)}` : ''))
const queueLabel = computed(() => queueWords(card))
const dueText = computed(() => {
  const date = day(card.due_date, card.due, today)
  return card.due_state ? `${card.due_state} ${date}` : date
})
const ageText = computed(() => {
  const column = STAGE_LABELS[stage]
  if (age === null || age < 1) return `In ${column} since today`
  return `${String(age)} day${age === 1 ? '' : 's'} in ${column}`
})
const showMeta = computed(
  () =>
    card.due !== '' ||
    total.value > 0 ||
    age !== null ||
    card.archived ||
    card.evidence_stage !== stage ||
    card.check !== null ||
    card.spent !== 0 ||
    card.budget !== null ||
    children.value > 0 ||
    card.pull !== null ||
    queueLabel.value !== '',
)
const spentTitle = computed(() =>
  spendTitle(
    card.budget !== null
      ? "Agent spend against the ticket's budget"
      : card.spent_estimated
        ? 'Cost of the agent runs on this ticket'
        : 'Cost reported by the agent runs on this ticket',
    card.spent_estimated,
  ),
)
const spendLevel = computed(() =>
  card.budget === null
    ? 'normal'
    : card.spent >= card.budget
      ? 'over'
      : card.spent >= card.budget * 0.8
        ? 'watch'
        : 'normal',
)
const SPEND_TEXT = {
  over: 'text-destructive',
  watch: 'text-foreground',
  normal: 'text-muted-foreground',
} as const
</script>

<template>
  <div
    v-if="showMeta"
    class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground"
  >
    <span
      v-if="card.due"
      class="flex items-center gap-1"
      :class="{
        'text-destructive font-medium': card.due_state === 'overdue',
        'text-foreground font-medium': card.due_state === 'soon',
      }"
      :title="`Due ${card.due}`"
      ><HugeiconsIcon :icon="Calendar03Icon" class="size-3.5 shrink-0" aria-hidden="true" />{{
        dueText
      }}</span
    >
    <span
      v-if="total"
      class="flex items-center gap-1"
      :class="{ 'text-foreground': done === total }"
      :title="`Checklist: ${done} of ${total} done`"
      ><svg class="size-3.5 -rotate-90" viewBox="0 0 36 36" aria-hidden="true">
        <circle
          cx="18"
          cy="18"
          r="15.9155"
          fill="none"
          stroke="currentColor"
          stroke-opacity="0.2"
          stroke-width="4"
        />
        <circle
          cx="18"
          cy="18"
          r="15.9155"
          fill="none"
          stroke="currentColor"
          stroke-width="4"
          stroke-linecap="round"
          :stroke-dasharray="`${Math.round((done * 100) / total)} 100`"
        /></svg
      >Checklist {{ done }}/{{ total }}</span
    >
    <span
      v-if="children"
      class="flex items-center gap-1"
      :class="{ 'text-foreground': childrenDone === children }"
      title="Child tickets done"
      ><HugeiconsIcon :icon="KanbanIcon" class="size-3.5 shrink-0" aria-hidden="true" />Child
      tickets {{ childrenDone }}/{{ children }}</span
    >
    <span
      v-if="age !== null"
      class="flex items-center gap-1"
      :class="{ 'text-foreground': age >= 7 && stage !== 'merged' && stage !== 'released' }"
      title="Time in this column"
      ><HugeiconsIcon :icon="Clock01Icon" class="size-3.5 shrink-0" aria-hidden="true" />{{
        ageText
      }}</span
    >
    <StatusBadge
      v-if="card.evidence_stage !== stage"
      key="evidence"
      tone="warning"
      :title="`Its branch, commits and pull request put it in ${STAGE_LABELS[card.evidence_stage]}, not ${STAGE_LABELS[stage]}`"
      >Git shows {{ STAGE_LABELS[card.evidence_stage] }}</StatusBadge
    >
    <span
      v-if="card.check"
      class="flex items-center gap-1"
      :class="card.check.passed ? 'text-foreground' : 'text-destructive'"
      :title="checkCommit"
      ><HugeiconsIcon
        :icon="card.check.passed ? Tick02Icon : Cancel01Icon"
        class="size-3.5 shrink-0"
        aria-hidden="true"
      />Checks {{ card.check.passed ? 'passed' : 'failed' }}</span
    >
    <a
      v-if="card.pull"
      :href="card.pull.url"
      class="flex items-center gap-1 hover:underline"
      title="The pull request on GitHub"
      ><HugeiconsIcon :icon="GitPullRequestIcon" class="size-3.5 shrink-0" aria-hidden="true" />PR
      #{{ pullNumber(card.pull.url) }} <PullLabel :card="card"
    /></a>
    <PullSize :pull="card.pull" />
    <span
      v-if="card.budget !== null"
      class="tabular-nums font-medium"
      :class="SPEND_TEXT[spendLevel]"
      :data-level="spendLevel"
      :title="spentTitle"
      >{{ cost(card.spent, card.spent_estimated) }} of {{ money(card.budget) }}</span
    >
    <span
      v-else-if="card.spent"
      class="tabular-nums font-medium text-muted-foreground"
      :title="spentTitle"
      >{{ cost(card.spent, card.spent_estimated) }}</span
    >
    <Badge v-if="card.archived" key="archived" variant="outline">Archived</Badge>
    <span
      v-if="queueLabel"
      class="text-muted-foreground"
      title="The agent queue: the agent working it, next to start, or what holds it"
      data-js-queue
      >{{ queueLabel }}</span
    >
  </div>
</template>
