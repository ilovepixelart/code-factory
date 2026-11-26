<script setup lang="ts">
import {
  CheckmarkCircle02Icon,
  CircleIcon,
  RecordIcon,
  Route01Icon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { TicketView } from '../../../lib/ticket'
import { Progress } from '@/components/ui/progress'
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceDescription,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from '@/components/ui/trace'

// AI Elements' Plan over the plan.md the agent wrote (CF-1219): its line names how far it has got,
// and opens on a bar and the steps, ticked as the commits that finish them land. The board does not
// know whether the agent is on a step now, so the first open step is next, not running. A step's
// state is in its words too, as its icon is hidden from assistive tech.
const { plan, headingId } = defineProps<{
  plan: NonNullable<TicketView['plan']>
  headingId: string
}>()

const next = computed(() => plan.items.findIndex((item) => !item.done))
const steps = computed(() =>
  plan.items.map((item, at) => {
    if (item.done) return { ...item, icon: CheckmarkCircle02Icon, words: 'done', pending: false }
    if (at === next.value) return { ...item, icon: RecordIcon, words: 'next', pending: false }
    return { ...item, icon: CircleIcon, words: 'to do', pending: true }
  }),
)
</script>

<template>
  <Trace>
    <TraceCollapsible default-open>
      <h4 :id="headingId">
        <TraceCollapsibleTrigger>
          <TraceLine>
            <TraceIcon><HugeiconsIcon :icon="Route01Icon" /></TraceIcon>
            <TraceTitle>Plan</TraceTitle>
            <TraceDescription>{{ plan.done }} of {{ plan.total }} done</TraceDescription>
          </TraceLine>
        </TraceCollapsibleTrigger>
      </h4>
      <TraceCollapsibleContent class="flex flex-col gap-2">
        <Progress
          :model-value="plan.total ? Math.round((plan.done * 100) / plan.total) : 0"
          aria-label="Plan progress"
        />
        <ul aria-label="Plan items" class="flex flex-col gap-1.5">
          <li v-for="(step, at) in steps" :key="at">
            <TraceLine v-bind="step.pending ? { status: 'pending' as const } : {}">
              <TraceIcon><HugeiconsIcon :icon="step.icon" /></TraceIcon>
              <TraceTitle
                >{{ step.text }}<span class="sr-only">, {{ step.words }}</span></TraceTitle
              >
            </TraceLine>
          </li>
        </ul>
      </TraceCollapsibleContent>
    </TraceCollapsible>
  </Trace>
</template>
