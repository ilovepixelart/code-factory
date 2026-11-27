<script setup lang="ts">
import EmptyLine from '../EmptyLine.vue'
import StatusBadge from '../StatusBadge.vue'
import SectionHeading from './SectionHeading.vue'
import { PlayIcon, StopIcon, Tick02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, useId } from 'vue'
import { act, Refused } from '../../lib/actions'
import { STAGE_LABELS } from '../../lib/board'
import { keys } from '../../lib/queryKeys'
import { failedStep } from '../../lib/standing'
import { cost, count, day, haltWords, money, spendLevel, spendTitle } from '../../lib/format'
import { announce, perform } from '../../lib/notice'
import { AGENT_STAGES, type TicketView } from '../../lib/ticket'
import Subagent from '../ai/Subagent/Subagent.vue'
import { Spinner } from '@/components/ui/spinner'
import { Trace } from '@/components/ui/trace'
import { useTicketForm } from './context'
import TicketAgentRun from './TicketAgentRun.vue'
import TicketStartOptions from './TicketStartOptions.vue'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'

// The agent working the ticket: its spend, its runs, the session subagents at work on it (CF-1184),
// and the controls that start, stop or review.
const { view, now } = defineProps<{ view: TicketView; now: number }>()
const uid = useId()

const { base, busy, refresh, task, send, press, spins } = useTicketForm()

const NEXT: Record<string, [string, string]> = {
  spec: ['the requirements, each with its named check', 'requirements.md'],
  build: ['the tests and the code, until the checks pass', ''],
}
// The board's own poll does not reach here: its ETag holds while only a run's log grows.
const SPEND_TEXT = {
  over: 'text-destructive',
  watch: 'text-foreground',
  normal: 'text-muted-foreground',
}

const agentMode = ref('bypassPermissions')
const agentLoop = ref(true)
const spend = computed(() => spendLevel(view.spent, view.budget))
const spentTitle = computed(() =>
  spendTitle(
    view.budget !== null ? "Agent spend against the ticket's budget" : 'Agent spend on this ticket',
    view.spent_estimated,
  ),
)
// The parts of the spend the runs reported (CF-651): the review's cost and share, turns, cache reads.
const breakdown = computed(() => {
  const { total, review, cache_read: cacheRead, turns } = view.cost
  const share = total ? ` (${String(Math.round((100 * (review ?? 0)) / total))}%)` : ''
  return [
    review ? `review ${money(review)}${share}` : '',
    turns === null ? '' : `${String(turns)} turns`,
    cacheRead === null ? '' : `${count(cacheRead)} cache reads`,
  ]
    .filter(Boolean)
    .join(' · ')
})
type MonthBudget = NonNullable<TicketView['month_budget']>
function monthEnding(m: MonthBudget): [string, string] {
  if (m.reached) return ['reached', 'text-destructive']
  if (m.runs_out) {
    return [`runs out ${day(m.runs_out, m.runs_out, m.runs_out)} at this pace`, 'text-foreground']
  }
  return ['lasts the month at this pace', 'text-muted-foreground']
}
// The repository's monthly budget (CF-671). `runs_out` always falls in the current month, so it is
// its own `today` and shows without its year.
const month = computed(() => {
  const m = view.month_budget
  if (!m) return null
  const [ending, tone] = monthEnding(m)
  return { text: `Month budget: ${money(m.spent)} of ${money(m.budget)}, ${ending}`, tone }
})
// Someone else at work holds the ticket as a run of its own does: no second agent is offered.
const workedBy = computed(() => view.card?.holder ?? view.subagents?.[0]?.name ?? '')
const next = computed(() => {
  const stage = view.current_stage
  const [what, file] = NEXT[stage] ?? ['', '']
  return { what, file }
})

// A finished build waits for review only when nothing else waits: an open question for its answer,
// an open review finding (as the findings section read them) for a fix.
const findings = useQuery<{ findings?: { state: string }[] }>({
  queryKey: computed(() => keys.findings(view.repository, String(view.ticket.id))),
  enabled: false,
})
const findingsOpen = computed(
  () => (findings.data.value?.findings ?? []).filter((f) => f.state === 'open').length,
)
const waitsForAnswer = computed(() => view.questions.some((q) => !q.answer))
// A failed ship or merge is what waits: the Status section says why and offers to try again.
const doneWords = computed(() => {
  const failed = failedStep(view.card?.delivery_event)
  if (failed) return `Its ${failed} failed: retry it from the alert under the title.`
  if (waitsForAnswer.value) return 'Waiting for an answer before review.'
  const open = findingsOpen.value
  if (open)
    return `A fix is due: ${String(open)} review ${open === 1 ? 'finding' : 'findings'} open.`
  return 'Done and waiting for review. An agent can check it against its spec first.'
})

async function startAgent(): Promise<void> {
  await send('runs', { permissions: agentMode.value, loop: agentLoop.value })
}

const splitOpen = ref(false)
const brief = ref('')
const splitRefusal = ref('')

// A refusal stays under the field with the brief still typed, unlike the panel's other actions.
async function startSplit(): Promise<void> {
  await task(async () => {
    splitRefusal.value = ''
    try {
      announce(await act('POST', `${base.value}/split`, { brief: brief.value }))
      brief.value = ''
      splitOpen.value = false
      await refresh()
    } catch (error) {
      splitRefusal.value = error instanceof Refused ? error.message : 'The board did not answer.'
    }
  })
}

async function reviewAgent(): Promise<void> {
  await send('reviews', {})
}

async function stopRun(run: string): Promise<void> {
  await task(() => perform(() => act('POST', `/api/runs/${encodeURIComponent(run)}/stop`), refresh))
}
</script>

<template>
  <section aria-labelledby="agent-heading">
    <SectionHeading id="agent-heading" class="mb-3"
      >Agent<span class="ml-auto text-sm font-normal"
        ><span
          v-if="view.budget !== null"
          class="tabular-nums font-medium"
          :class="SPEND_TEXT[spend]"
          :data-level="spend"
          :title="spentTitle"
          >{{ cost(view.spent, view.spent_estimated) }} of {{ money(view.budget) }}</span
        ><span
          v-else-if="view.spent"
          class="tabular-nums text-muted-foreground"
          :title="spentTitle"
          >{{ cost(view.spent, view.spent_estimated) }}</span
        ></span
      >
    </SectionHeading>
    <p
      v-if="month"
      aria-label="Month budget"
      class="mb-3 text-right text-sm tabular-nums"
      :class="month.tone"
      title="The repository's agent spend this UTC month against [agents] monthly_budget_usd, projected at its pace so far"
    >
      {{ month.text }}
    </p>
    <p
      v-if="breakdown"
      aria-label="Cost breakdown"
      class="text-muted-foreground mb-3 text-right text-sm tabular-nums"
      title="What the agent spend on this ticket is made of"
    >
      {{ breakdown }}
    </p>
    <p v-if="view.halted && !view.runs.length" class="mb-3">
      <StatusBadge tone="warning"
        ><HugeiconsIcon :icon="StopIcon" data-icon="inline-start" aria-hidden="true" />{{
          haltWords(view.halted)
        }}</StatusBadge
      >
    </p>
    <ul
      v-if="view.subagents?.length"
      aria-label="Session subagents at work"
      class="mb-3 flex flex-col gap-1.5"
    >
      <li v-for="agent in view.subagents" :key="agent.agent_id">
        <Trace><Subagent :agent="agent" :now="now" /></Trace>
      </li>
    </ul>
    <template v-if="view.runs.length">
      <TicketAgentRun
        v-for="run in view.runs"
        :key="run.id"
        :run="run"
        :now="now"
        :busy="busy"
        :stopping="spins(`stop ${run.id}`, busy)"
        @stop="press(`stop ${run.id}`, () => stopRun(run.id))"
      />
    </template>
    <p v-else-if="workedBy" class="text-muted-foreground text-sm">
      {{ workedBy }} is working on it.
    </p>
    <template v-else-if="AGENT_STAGES.includes(view.current_stage) && !view.work_done">
      <TicketStartOptions v-model:mode="agentMode" v-model:loop="agentLoop" />
      <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button
          type="button"
          class="gap-1.5"
          aria-describedby="agent-next"
          :disabled="busy"
          data-shortcut="start"
          @click="press('start', startAgent)"
        >
          <Spinner v-if="spins('start', busy)" data-icon="inline-start" />
          <HugeiconsIcon v-else :icon="PlayIcon" data-icon="inline-start" aria-hidden="true" />Start
          agent
        </Button>
        <Button type="button" variant="ghost" @click="splitOpen = !splitOpen"> Split </Button>
        <p
          id="agent-next"
          class="text-muted-foreground text-sm"
          title="Works on the ticket's branch in its own worktree"
        >
          Next: {{ next.what
          }}<template v-if="next.file"
            >, <span class="font-mono text-sm">{{ next.file }}</span></template
          >
        </p>
      </div>
      <form v-if="splitOpen" class="mt-3 grid gap-2" @submit.prevent="press('split', startSplit)">
        <Field :data-invalid="splitRefusal ? true : undefined">
          <FieldLabel :for="`${uid}-brief`">What to split this ticket into</FieldLabel>
          <Textarea
            :id="`${uid}-brief`"
            :model-value="brief"
            name="brief"
            rows="4"
            :aria-invalid="splitRefusal ? true : undefined"
            @update:model-value="brief = String($event)"
          />
          <FieldError v-if="splitRefusal">{{ splitRefusal }}</FieldError>
        </Field>
        <Button type="submit" class="justify-self-end" :disabled="busy || !brief.trim()">
          <Spinner v-if="spins('split', busy)" data-icon="inline-start" />Start split
        </Button>
      </form>
    </template>
    <div
      v-else-if="view.work_done && view.current_stage === 'build'"
      class="flex flex-wrap items-center gap-3"
    >
      <p class="text-muted-foreground text-sm">{{ doneWords }}</p>
      <Button
        v-if="!waitsForAnswer && findingsOpen"
        key="start"
        type="button"
        class="ml-auto gap-1.5"
        :disabled="busy"
        data-shortcut="start"
        @click="press('start', startAgent)"
      >
        <Spinner v-if="spins('start', busy)" data-icon="inline-start" />
        <HugeiconsIcon v-else :icon="PlayIcon" data-icon="inline-start" aria-hidden="true" />Start
        agent
      </Button>
      <Button
        v-else-if="!waitsForAnswer"
        key="review"
        type="button"
        variant="secondary"
        class="ml-auto"
        :disabled="busy"
        @click="press('review', reviewAgent)"
      >
        <Spinner v-if="spins('review', busy)" data-icon="inline-start" />
        <HugeiconsIcon
          v-else
          :icon="Tick02Icon"
          data-icon="inline-start"
          aria-hidden="true"
        />Review with an agent
      </Button>
    </div>
    <EmptyLine v-else>
      <Empty>
        <EmptyHeader>
          <EmptyDescription>{{
            `Nothing for an agent to do at ${STAGE_LABELS[view.current_stage]}.`
          }}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </EmptyLine>
  </section>
</template>
