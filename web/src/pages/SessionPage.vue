<script setup lang="ts">
import StatusBadge from '../components/StatusBadge.vue'
import SectionCard from '../components/SectionCard.vue'
import { Activity01Icon, ArrowDown01Icon, HelpCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, inject, reactive, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import ReadState from '../components/ReadState.vue'
import SessionFacts from '../components/SessionFacts.vue'
import TraceRows from '../components/TraceRows.vue'
import { ask, reasonOf, Refused, request } from '../lib/actions'
import type { Card as BoardCard } from '../lib/board'
import { clock, dur, short, thousands, trim } from '../lib/format'
import { BOARD } from '../lib/live'
import { refusalText } from '../lib/notice'
import { usePolledRead } from '../lib/queries'
import { keys, POLL } from '../lib/queryKeys'
import { turns, type Entry, type Session, type Turn, type Usage } from '../lib/sessions'
import { Button } from '@/components/ui/button'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { axisLength, traceRows } from '../lib/trace'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

// One session: its facts, then its
// turns with their entries; the latest and failed turns open. Follows changes.
// Entries asked for at first and added by each Show earlier: a long session's whole timeline is
// tens of megabytes (CF-1066).
const PAGE = 500

const route = useRoute()
const live = inject(BOARD)
live?.follow()
const id = computed(() => String(route.params.id ?? ''))
const session = ref<Session | null>(null)
const entries = shallowRef<Entry[]>([])
const total = ref(0)
const earlierPrompts = ref(0)
// How many of each session's latest entries are asked for; a session opened afresh starts at PAGE.
// It is read inside the timeline's read, not its key, so the cache keeps one timeline a session.
const shown = reactive<Record<string, number>>({})
const last = computed(() => shown[id.value] ?? PAGE)
const asking = ref(false)
const now = ref(Date.now() / 1000)
// A turn the person opened or closed keeps that choice across refreshes, until the session changes.
const chosen = ref<Record<number, boolean>>({})

interface Timeline {
  session: Session
  entries: Entry[]
  total: number
  earlier_prompts: number
}

// A 404 is an answer, the session is gone; any other refusal is a failed read.
const timeline = usePolledRead(
  () => keys.session(id.value),
  async (signal): Promise<Timeline | null> => {
    const path = `/api/sessions/${encodeURIComponent(id.value)}/timeline?last=${String(last.value)}`
    const response = await request(path, { signal })
    const body: unknown = await response.json().catch(() => null)
    if (response.status === 404) return null
    if (!response.ok) throw new Refused(reasonOf(body, response.status))
    return body as Timeline
  },
  POLL.session,
)
const refresh = timeline.refresh
const missing = computed(() => timeline.query.isSuccess.value && timeline.data.value === null)
// Once the session is shown, the page stands until the next tick reads it.
const failed = computed(() =>
  !session.value && timeline.query.error.value ? refusalText(timeline.query.error.value) : '',
)
watch(
  timeline.query.dataUpdatedAt,
  () => {
    now.value = Date.now() / 1000
    const answer = timeline.data.value
    if (!answer) return
    session.value = answer.session
    entries.value = answer.entries
    total.value = answer.total
    earlierPrompts.value = answer.earlier_prompts
  },
  { immediate: true },
)
// Usage reads the whole transcript, seconds for a long session: the timeline does not wait on it.
const usageWhere = computed(() => `/api/sessions/usage?session=${encodeURIComponent(id.value)}`)
const used = usePolledRead(
  () => keys.sessionUsage(usageWhere.value),
  (signal) => ask<Record<string, Usage>>(usageWhere.value, signal),
  POLL.session,
)
const usage = computed<Usage | null>(() => used.data.value?.[id.value] ?? null)

watch(id, () => {
  chosen.value = {}
})
async function showEarlier(): Promise<void> {
  asking.value = true
  shown[id.value] = last.value + PAGE
  // A poll sent before the click asked for fewer entries: it must not stand for this read.
  await refresh()
  asking.value = false
}

// Once a read settles without the session, the heading says so instead of loading.
const heading = computed(() => {
  if (session.value) return session.value.repository || 'unknown repository'
  if (missing.value) return 'Session not found'
  return failed.value ? `Session ${short(id.value)}` : 'Loading…'
})
const grouped = computed(() => turns(entries.value, earlierPrompts.value))
const shownWords = computed(() => {
  const n = entries.value.length
  const turnCount = grouped.value.length
  const turnWords = `${thousands(turnCount)} ${turnCount === 1 ? 'turn' : 'turns'}`
  if (n < total.value) {
    return `${turnWords}, latest ${thousands(n)} of ${thousands(total.value)} entries`
  }
  return `${turnWords}, ${thousands(n)} ${n === 1 ? 'entry' : 'entries'}`
})
// A stale session runs nothing: its open turn reads stale, as the Sessions list calls it.
function outcomeOf(turn: Turn): string {
  return turn.outcome === 'running' && session.value?.stale ? 'stale' : turn.outcome
}
function isOpen(index: number, byDefault: boolean): boolean {
  return chosen.value[index] ?? byDefault
}
const ticket = computed<BoardCard | undefined>(() => {
  for (const cards of Object.values(live?.board.value?.columns ?? {})) {
    const found = cards.find((c) => c.sessions.some((s) => s.session_id === id.value))
    if (found) return found
  }
  return undefined
})
</script>

<template>
  <Teleport to="#header-title">
    <Breadcrumb class="min-w-0">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink as-child><RouterLink to="/">Sessions</RouterLink></BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem class="min-w-0">
          <h1 class="truncate" :title="heading">
            <BreadcrumbPage>{{ heading }}</BreadcrumbPage>
          </h1>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  </Teleport>
  <div v-if="missing" class="page-wide">
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon"
          ><HugeiconsIcon :icon="HelpCircleIcon" aria-hidden="true"
        /></EmptyMedia>
        <EmptyTitle>{{ `No session ${id}` }}</EmptyTitle>
        <EmptyDescription>Open Sessions to find another session.</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button as-child variant="secondary"><RouterLink to="/">Sessions</RouterLink></Button>
      </EmptyContent>
    </Empty>
  </div>
  <div v-else-if="session" id="timeline-region" class="page-wide">
    <SessionFacts :session="session" :ticket="ticket" :usage="usage" :now="now" />
    <SectionCard
      heading="timeline-heading"
      title="Timeline"
      :count="grouped.length"
      :description="shownWords"
      :empty="!grouped.length"
    >
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Activity01Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>No events yet</EmptyTitle>
            <EmptyDescription
              >Messages and tool calls appear here as the session runs.</EmptyDescription
            >
          </EmptyHeader>
        </Empty>
      </template>
      <Button
        v-if="entries.length < total"
        type="button"
        variant="secondary"
        class="mb-2"
        :disabled="asking"
        @click="showEarlier()"
      >
        Show earlier
      </Button>
      <ol v-if="grouped.length" aria-label="Timeline" class="@container grid gap-3">
        <li v-for="turn in grouped" :key="turn.index" class="min-w-0 rounded-xl bg-card shadow-xs">
          <Collapsible
            :data-turn="turn.index"
            :open="isOpen(turn.index, turn.open_by_default)"
            :unmount-on-hide="false"
            @update:open="chosen[turn.index] = $event"
          >
            <CollapsibleTrigger
              class="group/turn flex w-full items-center gap-2 px-4 py-2.5 text-start text-sm"
            >
              <span class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span class="font-mono text-sm text-muted-foreground w-16 shrink-0">{{
                  clock(turn.started_at)
                }}</span>
                <span class="font-semibold">Turn {{ turn.index }}</span>
                <span v-if="turn.continued" class="text-muted-foreground">continued</span>
                <span v-else class="wrap-anywhere min-w-0" :title="turn.prompt_text">{{
                  trim(turn.prompt_text, 100) || 'no prompt captured'
                }}</span>
                <span class="text-muted-foreground text-sm"
                  >{{ turn.calls }} call{{ turn.calls !== 1 ? 's' : '' }}</span
                >
                <span v-if="turn.failed_calls" class="text-destructive text-sm"
                  >{{ turn.failed_calls }} failed</span
                >
                <span v-if="turn.duration_seconds !== null" class="text-muted-foreground text-sm">{{
                  dur(turn.duration_seconds)
                }}</span>
                <StatusBadge :state="outcomeOf(turn)" />
              </span>
              <HugeiconsIcon
                :icon="ArrowDown01Icon"
                class="ml-auto size-4 shrink-0 transition-transform group-data-[state=open]/turn:rotate-180"
                aria-hidden="true"
              />
            </CollapsibleTrigger>
            <CollapsibleContent class="px-4 pb-3">
              <div
                class="flex flex-wrap items-center gap-x-3 gap-y-0.5 @4xl:grid @4xl:grid-cols-[4rem_1rem_minmax(0,1fr)_6.5rem_4.5rem_8.5rem_14rem] ml-8 pl-4 text-sm text-muted-foreground tabular-nums @max-4xl:hidden"
                aria-hidden="true"
              >
                <span class="@4xl:col-start-7 flex justify-between"
                  ><span>0s</span><span>{{ dur(axisLength(turn)) }}</span></span
                >
              </div>
              <ol
                :aria-label="`Entries of turn ${turn.index}`"
                class="ml-2 grid grid-cols-1 gap-1.5 pb-1 pl-3 @4xl:ml-8 @4xl:pl-4"
              >
                <TraceRows
                  :rows="traceRows(turn, session)"
                  :session-id="session.session_id"
                  :cwd="session.cwd"
                />
              </ol>
            </CollapsibleContent>
          </Collapsible>
        </li>
      </ol>
    </SectionCard>
  </div>
  <ReadState v-else what="the session" :failed="failed" @retry="void refresh()" />
</template>
