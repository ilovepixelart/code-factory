<script setup lang="ts">
import { GitPullRequestIcon, Tick02Icon, UnavailableIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { STAGE_LABELS, pullNumber as numberOf, queueWords, type Stage } from '../../lib/board'
import { span } from '../../lib/format'
import type { TicketView } from '../../lib/ticket'
import { Button } from '@/components/ui/button'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import DeliveryStatus from '../DeliveryStatus.vue'
import StageGlyph from '../StageGlyph.vue'
import PullSize from '../PullSize.vue'
import StatusBadge from '../StatusBadge.vue'
import { useQuery } from '@tanstack/vue-query'
import { useDeliveryClock } from '../../lib/delivery'
import { keys } from '../../lib/queryKeys'
import { failedStep, failureWords, mergeItems as itemsOfMerge } from '../../lib/standing'
import { useTicketForm } from './context'

// Where the ticket stands, under its title (CF-1200), said once: one line of its stage (glyph, column
// and since when, what holds it, its queue place) with Archived, Blocked, its delivery and its pull
// request beside it; a quiet line of its time in each column and the conflict check; a failed ship or
// merge and a conflict found as an Alert; at Review, what the merge waits on. An archived ticket has
// no card and shows the stage line alone.
const { view } = defineProps<{ view: TicketView }>()

const COLUMNS: Stage[] = ['spec', 'build', 'review']

const card = computed(() => view.card ?? null)
// What holds it; empty when nothing does, and the `needs` clause is left out.
const hold = computed(() => card.value?.hold?.detail ?? '')
const queue = computed(() => (card.value ? queueWords(card.value) : ''))
const times = computed(() =>
  COLUMNS.map((column) => {
    const seconds = view.columns?.[column as 'spec' | 'build' | 'review'] ?? null
    const current = column === view.current_stage
    // A ticket in a column whose move was never recorded is there now, for an unknown time.
    if (seconds === null) return { column, text: current ? 'now' : 'not entered' }
    return { column, text: current ? `${span(seconds)} now` : span(seconds) }
  }),
)
// The column it is in and for how long; a column whose move was never recorded has no duration.
const stageLine = computed(() => {
  const label = STAGE_LABELS[view.current_stage]
  const seconds = view.columns?.[view.current_stage as 'spec' | 'build' | 'review'] ?? null
  return seconds === null ? `In ${label}` : `${label} for ${span(seconds)}`
})
// A failed ship or merge, with the press that tries it again; what a merge at Review waits on. The
// board's merge keeps the final word and refuses with its reason.
const { send, busy } = useTicketForm()
const clock = useDeliveryClock()
const event = computed(() => card.value?.delivery_event)
const failure = computed(() => failureWords(event.value, clock.value / 1000))
const failed = computed(() => failedStep(event.value))
const pull = computed(() => card.value?.pull ?? null)
const findings = useQuery<{ findings?: { state: string }[] }>({
  queryKey: computed(() => keys.findings(view.repository, String(view.ticket.id))),
  enabled: false,
})
const mergeItems = computed(() => {
  if (view.current_stage !== 'review' || !card.value) return []
  const open = (findings.data.value?.findings ?? []).filter((f) => f.state === 'open').length
  return itemsOfMerge(card.value, open)
})
const mergeReady = computed(
  () => mergeItems.value.length > 0 && mergeItems.value.every((item) => item.done),
)
const pullNumber = computed(() => (pull.value ? numberOf(pull.value.url) : ''))
const conflict = computed(() => view.status?.conflict ?? null)
const stage = computed((): Stage => view.current_stage)
const archived = computed(() => Boolean(view.ticket.archived))
const blocked = computed(() => Boolean(view.ticket.blocked))
</script>

<template>
  <section aria-label="Status" class="grid gap-3">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span
        class="inline-flex items-center gap-1.5 text-sm font-medium"
        data-header-stage
        data-status="stage"
        ><StageGlyph :stage="stage" decorative />{{ stageLine
        }}<span v-if="hold || queue" class="font-normal text-muted-foreground"
          ><template v-if="hold"> · needs {{ hold }}</template
          ><template v-if="queue"> · {{ queue }}</template></span
        ></span
      >
      <StatusBadge v-if="archived" key="archived" tone="quiet">Archived</StatusBadge>
      <StatusBadge v-if="blocked" key="blocked" tone="error"
        ><HugeiconsIcon
          :icon="UnavailableIcon"
          data-icon="inline-start"
          aria-hidden="true"
        />Blocked</StatusBadge
      >
      <DeliveryStatus v-if="card" :card="card" announce />
      <span v-if="pull" class="inline-flex items-center gap-2 text-sm" data-status="pull"
        ><a
          :href="pull.url"
          class="inline-flex items-center gap-1 underline underline-offset-4"
          target="_blank"
          rel="noopener noreferrer"
          ><HugeiconsIcon
            :icon="GitPullRequestIcon"
            class="size-3.5 shrink-0"
            aria-hidden="true"
          />#{{ pullNumber }}</a
        ><StatusBadge :state="pull.state" /><span
          v-if="pull.ci && pull.ci !== 'none'"
          :class="{ 'text-destructive': pull.ci === 'failed' }"
          >CI {{ pull.ci }}</span
        ><span v-if="pull.review" class="text-muted-foreground">review {{ pull.review }}</span
        ><PullSize :pull="pull"
      /></span>
    </div>
    <p
      v-if="card"
      class="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm text-muted-foreground"
    >
      <span class="tabular-nums" data-status="time"
        ><template v-for="(t, index) in times" :key="t.column"
          ><template v-if="index"> · </template
          ><span class="whitespace-nowrap"
            >{{ STAGE_LABELS[t.column] }} {{ t.text }}</span
          ></template
        ></span
      >
      <span v-if="conflict && !conflict.with" data-status="conflict">No conflict found</span>
      <a v-if="view.runs.length" href="#agent-heading" class="underline underline-offset-4"
        >Run details</a
      >
      <a v-if="view.check_log" href="#checklist-heading" class="underline underline-offset-4"
        >Check log</a
      >
    </p>
    <Alert v-if="failure" key="failure" variant="destructive" data-status="failure">
      <AlertDescription class="wrap-anywhere">{{ failure }}</AlertDescription>
      <AlertAction>
        <!-- Short, as the Alert keeps a narrow place for its action; its text says what failed. -->
        <Button
          type="button"
          variant="outline"
          size="sm"
          :aria-label="`Retry ${failed}`"
          :disabled="busy"
          @click="send(failed, {})"
          >Retry</Button
        >
      </AlertAction>
    </Alert>
    <Alert v-if="conflict?.with" key="conflict" variant="destructive" data-status="conflict">
      <AlertTitle>Merge conflict</AlertTitle>
      <AlertDescription class="wrap-anywhere"
        >Conflicts with {{ conflict.with }} in {{ conflict.files }}</AlertDescription
      >
    </Alert>
    <div v-if="mergeItems.length" class="flex flex-wrap items-end gap-3" data-status="merge">
      <ul class="grid gap-1 text-sm" aria-label="What the merge waits on">
        <li
          v-for="item in mergeItems"
          :key="item.text"
          :data-done="String(item.done)"
          class="flex items-center gap-2"
          :class="item.done ? '' : 'text-muted-foreground'"
        >
          <HugeiconsIcon
            v-if="item.done"
            :icon="Tick02Icon"
            class="size-3.5 shrink-0"
            aria-hidden="true"
          /><span
            v-else
            class="size-3.5 shrink-0 rounded-full border border-border"
            aria-hidden="true"
          />{{ item.text }}
        </li>
      </ul>
      <Button
        v-if="mergeReady"
        type="button"
        class="ml-auto gap-1.5"
        :disabled="busy"
        @click="send('merge', {})"
        ><HugeiconsIcon
          :icon="GitPullRequestIcon"
          data-icon="inline-start"
          aria-hidden="true"
        />Merge</Button
      >
    </div>
  </section>
</template>
