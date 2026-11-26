<script setup lang="ts">
import { entryPath, itemActions } from '../lib/itemActions'
import type { MemoryProposal } from '../lib/memory'
import MemoryQueue from './MemoryQueue.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'

// What `code-factory consolidate` proposes, listed on the Memory page and applied one at a time
// through the page's own merge and retire, with their notice and undo (CF-978); a queue drawn
// only while it holds a proposal (CF-1171-R1).
const { proposals } = defineProps<{ proposals: MemoryProposal[] }>()
const emit = defineEmits<{ changed: [] }>()
const { busy, errors, run } = itemActions(() => {
  emit('changed')
})
const keyOf = (p: MemoryProposal): string => `${p.repository}/${p.id}`

function words(p: MemoryProposal): string {
  return p.action === 'merge'
    ? `Merge "${p.statement}" into "${p.into_statement ?? ''}"`
    : `Retire "${p.statement}": ${p.reason ?? ''}`
}

function apply(p: MemoryProposal): Promise<void> {
  const base = entryPath(p.repository, p.id)
  return p.action === 'merge'
    ? run(keyOf(p), 'POST', `${base}/merge`, { into: p.into })
    : run(keyOf(p), 'POST', `${base}/retire`, { reason: p.reason })
}
</script>

<template>
  <MemoryQueue
    id="memory-consolidate"
    title="Proposed by consolidate"
    hint="each applied on its own, with Undo"
    :rows="proposals"
    :key-of="keyOf"
  >
    <template #row="{ row: p }">
      <div class="grid gap-1 px-4 py-3 text-sm">
        <div class="flex flex-wrap items-baseline gap-2">
          <span class="min-w-0 flex-1 wrap-anywhere">{{ words(p) }}</span>
          <Button
            type="button"
            variant="secondary"
            :disabled="busy.has(keyOf(p))"
            @click="apply(p)"
          >
            <Spinner v-if="busy.has(keyOf(p))" data-icon="inline-start" />Apply
          </Button>
        </div>
        <FieldError v-if="errors[keyOf(p)]">{{ errors[keyOf(p)] }}</FieldError>
      </div>
    </template>
  </MemoryQueue>
</template>
