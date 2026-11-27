<script setup lang="ts">
import { StopIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { computed } from 'vue'
import { runStageLabel } from '../../lib/board'
import { count, span } from '../../lib/format'
import type { RunProgress, TicketView } from '../../lib/ticket'
import RunMemory from './RunMemory.vue'

// One agent run of the ticket while it works: its iteration and stage, its progress from its own
// log, its memory, and the control that stops it.
const { run, now, busy, stopping } = defineProps<{
  run: TicketView['runs'][number]
  now: number
  busy: boolean
  /** Whether this run's stop is being sent. */
  stopping: boolean
}>()
const emit = defineEmits<{ stop: [] }>()

const UNKNOWN_PROGRESS: RunProgress = {
  tool_calls: null,
  reads: null,
  changes: null,
  files: null,
  tokens: null,
  last_activity: null,
}
const progress = computed(() => run.progress ?? UNKNOWN_PROGRESS)

// A run's progress (CF-1036), a number its log cannot give in words: it is not 0.
function progressLines(progress: RunProgress): string[] {
  const { tool_calls: calls, reads, changes, files, tokens, last_activity: last } = progress
  const plural = (n: number, noun: string): string => `${String(n)} ${noun}${n === 1 ? '' : 's'}`
  const tools =
    calls === null || reads === null || changes === null
      ? 'tool calls not known'
      : `${plural(calls, 'tool call')}: ${String(reads)} read, ${plural(changes, 'changed file')}, ${String(calls - reads - changes)} other`
  const tree =
    files === null
      ? 'files changed not known'
      : `${plural(files.count, 'file')} changed in its worktree`
  const spent = tokens === null ? 'tokens not known' : `${count(tokens)} tokens so far`
  const activity =
    last === null ? 'last activity not known' : `last activity ${span(now - last)} ago`
  return [tools, `${tree} · ${spent}`, activity]
}

function namedFiles(progress: RunProgress): string {
  const files = progress.files
  if (!files?.names.length) return ''
  const more = files.count - files.names.length
  return files.names.join(', ') + (more > 0 ? ` and ${String(more)} more` : '')
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-3">
    <span class="flex items-center gap-2 text-sm"
      ><Spinner />Iteration {{ run.iteration }} on {{ runStageLabel(run.stage) }}, started
      {{ span(now - run.started_at) }} ago<template v-if="run.loop">, looping</template></span
    >
    <Button
      type="button"
      variant="destructive"
      class="ml-auto"
      :disabled="busy"
      @click="emit('stop')"
    >
      <Spinner v-if="stopping" data-icon="inline-start" />
      <HugeiconsIcon v-else :icon="StopIcon" data-icon="inline-start" aria-hidden="true" />Stop
      agent
    </Button>
    <div aria-label="Run progress" class="text-muted-foreground w-full text-sm tabular-nums">
      <p v-for="line in progressLines(progress)" :key="line">{{ line }}</p>
      <p v-if="namedFiles(progress)" class="font-mono text-sm">
        {{ namedFiles(progress) }}
      </p>
    </div>
    <RunMemory :memory="run.memory" :context-at="run.context_at" :now="now" />
  </div>
</template>
