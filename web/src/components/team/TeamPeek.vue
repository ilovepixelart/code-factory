<script setup lang="ts">
import { sentence } from '../../lib/format'
import { Cancel01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useMediaQuery } from '@vueuse/core'
import { computed, onMounted, useTemplateRef, watch } from 'vue'
import { trapTab } from '../../lib/focusTrap'
import { clock, hourMinute, span } from '../../lib/format'
import { ticketHref } from '../../lib/ticket'
import {
  MILESTONE_LABELS,
  bar,
  pullWords,
  rowLine,
  type Peek,
  type TeamRow,
} from '../../lib/teamNow'
import StatusBadge from '../StatusBadge.vue'
import { Button } from '@/components/ui/button'

// The selected row's ticket (CF-1162): its milestones from filing against this cycle's medians and
// its last events. Beside the rows from lg up, a full sheet over the page below it: then a modal
// dialog, focus moves to its heading and Tab stays inside it.
const { row, peek, now } = defineProps<{ row: TeamRow; peek: Peek | undefined; now: number }>()
const emit = defineEmits<{ close: [] }>()
const filed = computed(() => peek?.milestones.find((m) => m.stage === 'filed')?.at ?? null)
const href = computed(() => (row.ticket ? ticketHref(row.ticket.repository, row.ticket.id) : ''))
const sheet = useMediaQuery('(max-width: 1023.98px)')
const aside = useTemplateRef<HTMLElement>('aside')
const title = useTemplateRef<HTMLElement>('title')
const attention = computed(() => row.state === 'owner' || row.state === 'stale')

/** A milestone's time words: when, and how long after filing; or how long so far. */
function reached(at: number | null): string {
  if (filed.value === null) return at === null ? 'not yet' : hourMinute(at)
  if (at === null) return `not yet · ${span(now - filed.value)} so far`
  return `${hourMinute(at)} · ${span(at - filed.value)}`
}

function enterSheet(): void {
  if (sheet.value) title.value?.focus()
}
onMounted(enterSheet)
watch(sheet, enterSheet)

function elapsed(at: number | null): number | null {
  if (filed.value === null) return null
  return (at ?? now) - filed.value
}
</script>

<template>
  <!-- An aside may not take the dialog role: the sheet is a div. -->
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -- the Tab key of the full sheet, a dialog while it is one -->
  <component
    :is="sheet ? 'div' : 'aside'"
    ref="aside"
    :role="sheet ? 'dialog' : undefined"
    :aria-modal="sheet ? 'true' : undefined"
    :tabindex="sheet ? -1 : undefined"
    class="fixed inset-0 z-30 overflow-y-auto bg-background p-4 lg:sticky lg:inset-auto lg:top-0 lg:z-auto lg:max-h-full lg:w-96 lg:shrink-0 lg:self-start lg:border-l lg:border-border lg:bg-transparent"
    aria-labelledby="team-peek-title"
    @keydown.tab="sheet && trapTab($event, aside)"
  >
    <div class="mb-2 flex items-center gap-2">
      <span class="font-mono text-sm">{{ row.ticket?.id }}</span>
      <StatusBadge :state="row.state" :quiet="!attention" />
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        class="ml-auto"
        aria-label="Close"
        @click="emit('close')"
      >
        <HugeiconsIcon :icon="Cancel01Icon" aria-hidden="true" />
      </Button>
    </div>
    <h3 id="team-peek-title" ref="title" tabindex="-1" class="text-sm font-semibold outline-none">
      {{ row.ticket?.title || row.ticket?.id }}
    </h3>
    <p class="text-muted-foreground mt-1 text-sm">
      <template v-if="peek">{{ sentence(peek.type) }} · {{ peek.column }} · </template
      ><template v-if="row.pull"
        ><a :href="row.pull.url" class="underline-offset-4 hover:underline"
          >#{{ row.pull.number }}</a
        >
        {{ pullWords(row.pull) }} · </template
      >{{ rowLine(row) }}
    </p>
    <template v-if="peek">
      <h4 class="text-xs font-medium tracking-wider text-muted-foreground uppercase mt-5 mb-2">
        Stage times from filing
      </h4>
      <ol class="grid gap-2 text-sm" aria-label="Stage times from filing">
        <li
          v-for="milestone in peek.milestones"
          :key="milestone.stage"
          class="grid grid-cols-[6rem_minmax(0,1fr)_auto] items-baseline gap-x-2 gap-y-1"
          :data-milestone="milestone.stage"
        >
          <span class="text-muted-foreground">{{ MILESTONE_LABELS[milestone.stage] }}</span>
          <span :class="milestone.at === null ? 'text-muted-foreground' : ''">{{
            reached(milestone.at)
          }}</span>
          <span class="text-muted-foreground tabular-nums"
            ><template v-if="milestone.cycle !== null"
              >cycle {{ span(milestone.cycle) }}</template
            ></span
          >
          <span
            v-if="milestone.stage !== 'filed'"
            class="relative col-start-2 col-end-4 h-1 rounded-full bg-muted"
            aria-hidden="true"
            ><span
              class="absolute inset-y-0 left-0 rounded-full"
              :class="milestone.at === null ? 'bg-foreground/15' : 'bg-foreground/35'"
              :style="{ width: `${bar(elapsed(milestone.at), milestone.cycle).fill}%` }"
            ></span
            ><span
              v-if="milestone.cycle !== null"
              class="absolute -inset-y-1 w-0.5 rounded-full bg-foreground"
              :style="{ left: `${bar(elapsed(milestone.at), milestone.cycle).mark}%` }"
            ></span
          ></span>
        </li>
      </ol>
      <h4 class="text-xs font-medium tracking-wider text-muted-foreground uppercase mt-5 mb-2">
        Last events
      </h4>
      <ol class="grid gap-1.5 text-sm" aria-label="Last events">
        <li
          v-for="event in peek.events"
          :key="`${String(event.at)}-${event.words}`"
          class="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-2"
        >
          <span class="text-muted-foreground font-mono text-sm tabular-nums">{{
            clock(event.at)
          }}</span
          ><span class="break-words">{{ event.words }}</span>
        </li>
      </ol>
    </template>
    <p v-if="href" class="mt-5 flex gap-4 text-sm">
      <RouterLink :to="href" class="underline-offset-4 hover:underline"
        >Open {{ row.ticket?.id }}</RouterLink
      >
      <RouterLink :to="`${href}#activity-heading`" class="underline-offset-4 hover:underline"
        >All its activity</RouterLink
      >
    </p>
  </component>
</template>
