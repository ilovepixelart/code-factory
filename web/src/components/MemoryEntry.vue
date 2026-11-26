<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import { sentence } from '../lib/format'
import { ArrowDown01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import StatusBadge from './StatusBadge.vue'
import { Badge } from '@/components/ui/badge'
import { createReusableTemplate } from '@vueuse/core'
import { computed, inject, nextTick, ref, useTemplateRef } from 'vue'
import { act } from '../lib/actions'
import { day } from '../lib/format'
import { BOARD } from '../lib/live'
import { dateOf, loadsElsewhere, statementOf, type MemoryRecord } from '../lib/memory'
import { announce } from '../lib/notice'
import { refusalText } from '../lib/notice'
import MemoryForm, { type MemoryDraft } from './MemoryForm.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Item, ItemTitle } from '@/components/ui/item'
import { FieldError } from '@/components/ui/field'
import MemoryReview from './MemoryReview.vue'

// One active memory entry: what it says, why, where from, whether it still holds, and the
// review actions, each opening its form in place of the entry's actions. As a `row` it is closed
// until opened (CF-1171-R4); as a `due` item of Review due it is open, with Still holds or Add a
// source first (CF-1171-R5).
const {
  record,
  others,
  variant = 'row',
  opened,
  overdue,
} = defineProps<{
  record: MemoryRecord
  others: MemoryRecord[]
  variant?: 'row' | 'due'
  opened?: boolean
  /** A due item whose review date passed (CF-1171-R5). */
  overdue?: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const [DefineWork, Work] = createReusableTemplate()
const [DefineMeta, Meta] = createReusableTemplate()
const [DefineGuard, Guard] = createReusableTemplate()
const [DefineFlags, Flags] = createReusableTemplate()

type Mode = 'view' | 'edit' | 'merge' | 'retire' | 'source'
const mode = ref<Mode>('view')
const busy = ref(false)
const error = ref('')
const card = useTemplateRef<HTMLElement>('card')
let opener: Mode = 'view'

const base = computed(
  () => `/api/memory/${encodeURIComponent(record.repository)}/${encodeURIComponent(record.id)}`,
)
const start = computed<MemoryDraft>(() => ({
  kind: record.kind,
  statement: record.statement,
  why: record.why,
  source: record.source,
  guard: record.guard,
  scope: record.scope,
}))
const live = inject(BOARD, undefined)
const today = computed(() => live?.board.value?.today ?? dateOf(Date.now() / 1000))
const when = (date: string): string => day(date, date, today.value)
const runs = computed(() => record.received_count ?? record.received_by.length)
const received = computed(() => {
  if (!runs.value) return 'No run has received it yet'
  const count = `${String(runs.value)} ${runs.value === 1 ? 'run' : 'runs'}`
  return record.last_received ? `${count}, last received ${when(record.last_received)}` : count
})
const tickets = computed(() => [...new Set(record.received_by.map((r) => r.ticket_id))])
const sourceless = computed(() => record.source.trim() === '')
const targets = computed(() =>
  others.filter((o) => o.repository === record.repository && o.id !== record.id),
)

function submitWork(answer: string): Promise<void> {
  if (mode.value === 'source') return send('PATCH', base.value, { source: answer.trim() })
  if (mode.value === 'merge') return send('POST', `${base.value}/merge`, { into: answer })
  return send('POST', `${base.value}/retire`, { reason: answer })
}

function open(next: Mode): void {
  error.value = ''
  mode.value = next
  opener = next
  void focusForm()
}

// Opening a form unmounts the button that opened it: focus goes to the form's first field (the
// edit form focuses its own statement), and back to that button, or to the row, when it closes.
async function focusForm(): Promise<void> {
  await nextTick()
  if (mode.value !== 'edit') {
    card.value?.querySelector<HTMLElement>('form input, form select, form textarea')?.focus()
  }
}

async function close(): Promise<void> {
  mode.value = 'view'
  await nextTick()
  const place =
    card.value?.querySelector<HTMLElement>(`[data-opens="${opener}"]`) ??
    card.value?.querySelector<HTMLElement>('summary') ??
    card.value
  if (!place) return
  if (place === card.value) place.tabIndex = -1
  place.focus()
}

async function send(method: 'PATCH' | 'POST', path: string, body: object): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    announce(await act(method, path, body))
    emit('changed')
    void close()
  } catch (failure) {
    error.value = refusalText(failure)
  }
  busy.value = false
}

function save(draft: MemoryDraft): void {
  void send('PATCH', base.value, draft)
}
</script>

<template>
  <DefineMeta>
    <span class="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <Badge variant="outline">{{ sentence(record.kind) }}</Badge>
      <span v-if="record.source">{{ record.source }}</span>
      <StatusBadge v-else tone="warning">No source</StatusBadge>
      <span>{{ record.repository }}</span>
      <StatusBadge v-if="record.stale_cites?.length" key="badge-2" tone="warning"
        >Cites gone: {{ record.stale_cites.join(', ') }}</StatusBadge
      >
      <StatusBadge v-if="record.unused" key="badge-3" tone="warning"
        >No run received it in 30 days</StatusBadge
      >
      <StatusBadge
        v-if="overdue && !record.stale_cites?.length && !record.unused"
        key="badge-4"
        tone="warning"
        :title="record.review_due"
        >Review was due {{ when(record.review_due) }}</StatusBadge
      >
      <Guard />
      <Flags />
    </span>
  </DefineMeta>
  <DefineGuard>
    <span v-if="loadsElsewhere(record)">{{ record.loads }}</span>
    <StatusBadge v-if="record.guard_state === 'enforced'" key="badge-1" tone="success"
      >Enforced by <span class="font-mono text-sm">{{ record.guard }}</span></StatusBadge
    >
    <StatusBadge v-else-if="record.guard_state === 'missing'" key="badge-2" tone="error"
      >Guard missing: <span class="font-mono text-sm">{{ record.guard }}</span></StatusBadge
    >
    <Badge v-else-if="record.guard_state === 'none'" key="badge-3" variant="outline"
      >no guard</Badge
    >
  </DefineGuard>
  <DefineFlags>
    <StatusBadge v-if="record.left_out" tone="error">Left out</StatusBadge>
    <Badge v-if="record.superseded_by" key="badge-2" variant="outline"
      >superseded by "{{ statementOf(record.repository, record.superseded_by, others) }}"</Badge
    >
    <StatusBadge v-if="record.filing !== 'committed'" key="badge-3" tone="warning"
      >Not filed</StatusBadge
    >
  </DefineFlags>
  <DefineWork>
    <MemoryForm
      v-if="mode === 'edit'"
      name="Edit the entry"
      :start="start"
      submit="Save and mark reviewed"
      :error="error"
      :busy="busy"
      @save="save($event)"
      @cancel="close()"
    />
    <div v-else-if="mode === 'view'" class="mt-1 flex flex-wrap gap-2">
      <Button
        v-if="variant === 'due' && sourceless"
        key="source"
        type="button"
        variant="secondary"
        :disabled="busy"
        data-opens="source"
        @click="open('source')"
      >
        <Spinner v-if="busy" data-icon="inline-start" />Add a source
      </Button>
      <Button
        v-else
        key="review"
        type="button"
        variant="secondary"
        :disabled="busy"
        @click="send('PATCH', base, {})"
      >
        <Spinner v-if="busy" data-icon="inline-start" />{{
          variant === 'due' ? 'Still holds' : 'Mark reviewed'
        }}
      </Button>
      <Button type="button" variant="secondary" data-opens="edit" @click="open('edit')"
        >Edit</Button
      >
      <Button
        v-if="variant === 'row'"
        key="merge"
        type="button"
        variant="secondary"
        :disabled="!targets.length"
        data-opens="merge"
        @click="open('merge')"
      >
        Merge
      </Button>
      <Button type="button" variant="secondary" data-opens="retire" @click="open('retire')"
        >Retire</Button
      >
    </div>
    <MemoryReview
      v-else
      :mode="mode"
      :targets="targets"
      :busy="busy"
      :error="error"
      @submit="submitWork($event)"
      @cancel="close()"
    />
    <FieldError v-if="mode === 'view' && error">{{ error }}</FieldError>
  </DefineWork>

  <ContentCard
    v-if="variant === 'row'"
    :id="record.id"
    role="listitem"
    :aria-label="record.statement"
    class="scroll-mt-4"
  >
    <Item class="py-3">
      <details ref="card" :open="opened" class="group/disclosure w-full min-w-0">
        <summary
          class="grid cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-1 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4"
        >
          <ItemTitle class="line-clamp-none wrap-anywhere">{{ record.statement }}</ItemTitle>
          <HugeiconsIcon
            :icon="ArrowDown01Icon"
            class="size-4 self-center opacity-60 group-open/disclosure:rotate-180"
            aria-hidden="true"
          />
          <span
            class="text-muted-foreground col-span-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
          >
            <Badge variant="outline">{{ sentence(record.kind) }}</Badge>
            <span v-if="record.source">{{ record.source }}</span>
            <span v-if="record.review_due" :title="record.review_due"
              >review by {{ when(record.review_due) }}</span
            >
            <StatusBadge v-if="record.guard_state === 'missing'" tone="error"
              >Guard missing: <span class="font-mono text-sm">{{ record.guard }}</span></StatusBadge
            >
            <Flags />
          </span>
        </summary>
        <div class="grid gap-2 pt-3">
          <span v-if="record.why" class="text-muted-foreground wrap-anywhere"
            >Why: {{ record.why }}</span
          >
          <span v-else class="text-muted-foreground text-sm">No why recorded</span>
          <span class="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span :title="record.date">{{ when(record.date) }}</span>
            <span>{{ record.repository }}</span>
            <span :title="record.last_received || undefined">{{ received }}</span>
            <template v-if="record.guard_state !== 'missing'"><Guard /></template>
            <span v-else-if="loadsElsewhere(record)">{{ record.loads }}</span>
            <Badge
              v-if="!record.loaded && !record.left_out && !record.superseded_by"
              variant="outline"
              >not loaded</Badge
            >
          </span>
          <span v-if="tickets.length" class="text-muted-foreground text-sm wrap-anywhere"
            >Received by runs of {{ tickets.join(', ') }}</span
          >
          <Work />
        </div>
      </details>
    </Item>
  </ContentCard>
  <article v-else ref="card" :aria-label="record.statement" class="grid gap-1 px-4 py-3 text-sm">
    <div class="flex items-baseline gap-3">
      <span class="min-w-0 flex-1 wrap-anywhere">{{ record.statement }}</span>
      <span
        class="text-muted-foreground shrink-0 text-sm"
        :title="record.reviewed || record.date"
        >{{ when(record.reviewed || record.date) }}</span
      >
    </div>
    <Meta />
    <Work />
  </article>
</template>
