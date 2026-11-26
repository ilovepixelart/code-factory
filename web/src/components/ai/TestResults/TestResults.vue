<script setup lang="ts">
import { TestTube01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { TicketView } from '../../../lib/ticket'
import Terminal from '../Terminal/Terminal.vue'
import { CodeBlock, CodeBlockContent } from '@/components/ui/code-block'
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from '@/components/ui/trace'

// AI Elements' Test Results over the board's checks: the latest run as a line, open when it
// failed, with the failing lines and the whole output folded under them. The board keeps a run's
// log, not its tests, so the failing lines stand in for the failed tests.
const { check, log } = defineProps<{ check: NonNullable<TicketView['check']>; log: string }>()

// A line naming a failure; test names join words with `_`, so `a_failed_x` names none.
const FAILURE = /\b(fail|failed|error|panicked)\b/i
const lines = computed(() => log.split('\n'))
// The failing lines, else the last line, where a gate says how it ended.
const failing = computed(() => {
  const found = lines.value.filter((line) => FAILURE.test(line))
  return (found.length > 0 ? found : lines.value.slice(-1)).join('\n')
})
const failed = computed(() => check.exit_code !== 0)
const title = computed(() => {
  const commit = check.commit.slice(0, 7) || 'no commit'
  if (!failed.value) return `Checks passed on ${commit}`
  const reason = check.reason ? `${check.reason}, ` : ''
  return `Checks failed on ${commit}, ${reason}exit code ${String(check.exit_code)}`
})
</script>

<template>
  <Trace>
    <TraceCollapsible v-if="log" :default-open="failed" :unmount-on-hide="false">
      <TraceCollapsibleTrigger>
        <TraceLine v-bind="failed ? { status: 'error' as const } : {}">
          <TraceIcon><HugeiconsIcon :icon="TestTube01Icon" /></TraceIcon>
          <TraceTitle>{{ title }}</TraceTitle>
        </TraceLine>
      </TraceCollapsibleTrigger>
      <TraceCollapsibleContent class="flex flex-col gap-1.5">
        <CodeBlock size="sm">
          <CodeBlockContent wrap class="max-h-64" aria-label="Failing lines">{{
            failing
          }}</CodeBlockContent>
        </CodeBlock>
        <Trace>
          <Terminal
            :title="`Whole output, ${String(lines.length)} lines`"
            :output="log"
            label="Checks output"
          />
        </Trace>
      </TraceCollapsibleContent>
    </TraceCollapsible>
    <TraceLine v-else v-bind="failed ? { status: 'error' as const } : {}">
      <TraceIcon><HugeiconsIcon :icon="TestTube01Icon" /></TraceIcon>
      <TraceTitle>{{ title }}</TraceTitle>
    </TraceLine>
  </Trace>
</template>
