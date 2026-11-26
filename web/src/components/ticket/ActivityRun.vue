<script setup lang="ts">
import StatusBadge from '../StatusBadge.vue'
import { computed } from 'vue'
import { STAGE_LABELS, type Stage } from '../../lib/board'
import { count, span } from '../../lib/format'
import type { ActivityEntry } from '../../lib/ticket'
import { statusWord } from '../../lib/status_tone'
import StageGlyph from '../StageGlyph.vue'
import RunMemory from './RunMemory.vue'
import { Button } from '@/components/ui/button'

// One run in a ticket's activity (CF-1075): who ran it on what, how it ended, what it took.
const { entry, now } = defineProps<{ entry: ActivityEntry; now: number }>()

const stage = computed(() => (entry.stage ?? '') as Stage)
const outcome = computed(() => {
  const said = entry.outcome ?? 'running'
  return said === 'failed' &&
    !entry.text &&
    entry.exit_code !== null &&
    entry.exit_code !== undefined
    ? `failed · exit ${String(entry.exit_code)}`
    : said
})
const meta = computed(() =>
  [
    typeof entry.duration === 'number' ? span(entry.duration) : '',
    typeof entry.tokens === 'number' ? `${count(entry.tokens)} tokens` : '',
  ]
    .filter(Boolean)
    .join(' · '),
)
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-3 gap-y-1" data-run>
    <span class="font-medium">{{ entry.agent || 'Agent' }}</span>
    <span v-if="entry.model" class="font-mono text-muted-foreground text-sm">{{
      entry.model
    }}</span>
    <span class="text-muted-foreground inline-flex items-center gap-1.5 text-sm"
      ><StageGlyph :stage="stage" decorative />{{ STAGE_LABELS[stage] ?? entry.stage
      }}<template v-if="(entry.iteration ?? 1) > 1">
        · iteration {{ entry.iteration }}</template
      ></span
    >
    <StatusBadge :state="entry.outcome ?? 'running'">{{ statusWord(outcome) }}</StatusBadge>
    <span v-if="meta" class="text-muted-foreground text-sm tabular-nums">{{ meta }}</span>
    <span class="ml-auto flex items-center gap-2" data-age>
      <Button
        v-if="entry.run"
        as-child
        variant="ghost"
        size="xs"
        target="_blank"
        rel="noopener noreferrer"
        ><a :href="`/api/runs/${encodeURIComponent(entry.run)}/log`">Log</a></Button
      >
      <span class="text-muted-foreground text-sm tabular-nums">{{ span(now - entry.at) }} ago</span>
    </span>
    <RunMemory :memory="entry.memory" :context-at="entry.context_at ?? null" :now="now" />
  </div>
</template>
