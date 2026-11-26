<script setup lang="ts">
import SectionHeading from './SectionHeading.vue'
import { PlayIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { TicketView } from '../../lib/ticket'
import TestResults from '../ai/TestResults/TestResults.vue'
import Terminal from '../ai/Terminal/Terminal.vue'
import TicketSummary from './TicketSummary.vue'
import { useTicketForm } from './context'
import { Button } from '@/components/ui/button'
import { Trace } from '@/components/ui/trace'
import { Spinner } from '@/components/ui/spinner'

// The ticket's checks: the latest run, what the ticket proved and the failing lines (CF-1206 took
// out the strip of steps and the fold of where the board looks, which repeated Status).
const { view } = defineProps<{ view: TicketView }>()

const { busy, send, press, spins } = useTicketForm()

async function runChecks(): Promise<void> {
  await send('checks', {})
}
// Before Build no check runs, so an unchecked repository says nothing about checks there (CF-1081);
// after the merge nothing can be added, so only what was recorded shows (CF-1087).
const settled = computed(() => ['merged', 'released'].includes(view.current_stage))
const checksShown = computed(
  () =>
    view.check !== null ||
    (!settled.value && (view.checks_configured || view.current_stage !== 'spec')),
)
const summaryShown = computed(() => {
  if (view.current_stage === 'review') return true
  const { gate, verdict, capture } = view.summary
  return settled.value && Boolean(gate ?? capture ?? verdict)
})
// Nothing to say of a ticket with no checks, summary or log: no empty heading.
const shown = computed(() => checksShown.value || summaryShown.value || Boolean(view.runner_log))
</script>

<template>
  <section v-if="shown" aria-labelledby="checklist-heading">
    <SectionHeading id="checklist-heading" class="mb-3"> Checks </SectionHeading>
    <div
      v-if="checksShown"
      class="flex flex-wrap items-start gap-3 rounded-xl bg-muted/50 px-3 py-2.5 text-sm"
      aria-label="Checks"
    >
      <TestResults
        v-if="view.check"
        :check="view.check"
        :log="view.check_log"
        class="min-w-0 flex-1"
      />
      <span v-else-if="view.checks_configured" class="text-muted-foreground"
        >Checks not run yet. Build is done when they pass on the branch head.</span
      >
      <span v-else class="text-muted-foreground"
        >No checks command. Add <span class="font-mono text-sm">[checks] command = "..."</span> to
        <span class="font-mono text-sm">.code-factory/config.toml</span> so Build is verified.</span
      >
      <Button
        v-if="view.checks_configured && !view.checking"
        type="button"
        variant="ghost"
        size="xs"
        class="ml-auto gap-1"
        :disabled="busy"
        data-shortcut="checks"
        @click="press('checks', runChecks)"
      >
        <Spinner v-if="spins('checks', busy)" data-icon="inline-start" />
        <HugeiconsIcon v-else :icon="PlayIcon" data-icon="inline-start" aria-hidden="true" />Run
        checks
      </Button>
    </div>
    <TicketSummary v-if="summaryShown" :summary="view.summary" />
    <Trace v-if="view.runner_log" class="mt-2">
      <Terminal title="Runner's log" :output="view.runner_log" label="Runner's log" />
    </Trace>
  </section>
</template>
